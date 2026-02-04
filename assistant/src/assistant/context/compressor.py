import asyncio
import logging
from typing import Any, Optional

from .prompts import CONTEXT_SEGMENT_SUMMARY_PROMPT

logger = logging.getLogger(__name__)


class ContextCompressor:
    def __init__(self, llm: Any, message_builder: Any):
        self.llm = llm
        self.message_builder = message_builder
        self._last_fallback_used = False

    @property
    def last_fallback_used(self) -> bool:
        return self._last_fallback_used

    async def summarize_segment(
        self,
        segment: str,
        index: int,
        total: int,
        *,
        existing_summary: str = "",
    ) -> str:
        if not self.llm:
            return ""
        user_prompt = (
            f"已有摘要（可能为空）：\n{existing_summary}\n\n"
            f"新增分段（{index + 1}/{total}）：\n{segment}\n\n"
            "请输出更新后的摘要："
        )
        try:
            response = await self.llm.agenerate(
                messages=self.message_builder(CONTEXT_SEGMENT_SUMMARY_PROMPT, user_prompt),
                tools=None,
            )
            return response.text.strip() if response else ""
        except Exception as e:
            logger.warning("segment summary failed: %s", e)
            return ""

    async def summarize_segments(
        self,
        segments: list[str],
        *,
        skip_indices: set[int] | None = None,
        max_concurrency: int = 4,
        fuse: bool = True,
        fuse_max_chars: int = 2000,
        fallback_strategy: str = "heuristic",
        fallback_max_chars: int = 2000,
        fallback_max_segments: int = 12,
    ) -> str:
        if not segments:
            return ""
        self._last_fallback_used = False
        if not self.llm:
            self._last_fallback_used = True
            return self._fallback_summary(
                segments,
                skip_indices=skip_indices,
                strategy=fallback_strategy,
                max_chars=fallback_max_chars,
                max_segments=fallback_max_segments,
            )
        skip_indices = skip_indices or set()
        indices = [i for i in range(len(segments)) if i not in skip_indices]
        if not indices:
            return ""

        async def summarize_one(idx: int) -> tuple[int, str]:
            text = segments[idx]
            prompt = (
                f"分段（{idx + 1}/{len(segments)}）：\n{text}\n\n"
                "请输出该分段的结构化摘要："
            )
            try:
                response = await self.llm.agenerate(
                    messages=self.message_builder(CONTEXT_SEGMENT_SUMMARY_PROMPT, prompt),
                    tools=None,
                )
                return idx, response.text.strip() if response else ""
            except Exception as e:
                logger.warning("segment summary failed: idx=%s err=%s", idx, e)
                return idx, ""

        semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))

        async def run(idx: int) -> tuple[int, str]:
            async with semaphore:
                return await summarize_one(idx)

        results = await asyncio.gather(*(run(i) for i in indices))
        results.sort(key=lambda x: x[0])
        merged = []
        for _idx, text in results:
            if text:
                merged.append(text)
        merged_text = "\n".join(merged)
        if not merged_text:
            self._last_fallback_used = True
            return self._fallback_summary(
                segments,
                skip_indices=skip_indices,
                strategy=fallback_strategy,
                max_chars=fallback_max_chars,
                max_segments=fallback_max_segments,
            )
        if not fuse:
            return merged_text
        return await self._fuse_summaries(merged_text, fuse_max_chars=fuse_max_chars)

    async def _fuse_summaries(self, summaries_text: str, *, fuse_max_chars: int) -> str:
        if not self.llm:
            return summaries_text
        text = summaries_text
        if fuse_max_chars and len(text) > fuse_max_chars:
            text = text[:fuse_max_chars]
        user_prompt = (
            "以下是多个分段摘要，请进行二次融合，输出统一的结构化摘要：\n"
            f"{text}\n\n"
            "请输出融合后的摘要："
        )
        try:
            response = await self.llm.agenerate(
                messages=self.message_builder(CONTEXT_SEGMENT_SUMMARY_PROMPT, user_prompt),
                tools=None,
            )
            return response.text.strip() if response else summaries_text
        except Exception as e:
            logger.warning("summary fuse failed: %s", e)
            return summaries_text

    def _fallback_summary(
        self,
        segments: list[str],
        *,
        skip_indices: set[int] | None,
        strategy: str,
        max_chars: int,
        max_segments: int,
    ) -> str:
        if not segments:
            return ""
        skip_indices = skip_indices or set()
        candidates = [s for i, s in enumerate(segments) if i not in skip_indices and s.strip()]
        if not candidates:
            return ""
        if strategy == "none":
            return ""
        if strategy == "truncate":
            text = "\n".join(candidates[: max(1, int(max_segments))])
            return text[: max(200, int(max_chars))].strip()
        # heuristic: keep first/last sentence of each segment
        picked = []
        for seg in candidates[: max(1, int(max_segments))]:
            seg = seg.strip()
            if not seg:
                continue
            parts = [p for p in seg.split("\n") if p.strip()]
            if len(parts) == 1:
                picked.append(parts[0])
            else:
                picked.append(parts[0])
                if len(picked) >= max_segments:
                    break
                picked.append(parts[-1])
        text = "\n".join(picked)
        return text[: max(200, int(max_chars))].strip()
