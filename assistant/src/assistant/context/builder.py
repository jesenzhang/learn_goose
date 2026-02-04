import json
import logging
import re
from typing import Any, Dict, List, Optional

from .config import ContextConfig
from .interfaces import RecallProvider, TokenCounter
from .models import ContextAnalysis, ContextProcessResult, RequirementExtraction, RecallSummary
from .prompts import REQUIREMENT_CLASSIFIER_PROMPT, REQUIREMENT_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class ContextBuilder:
    def __init__(
        self,
        *,
        config: ContextConfig,
        token_counter: TokenCounter,
        llm: Any = None,
        message_builder: Optional[Any] = None,
        recall_provider: Optional[RecallProvider] = None,
    ) -> None:
        self.config = config
        self.token_counter = token_counter
        self.llm = llm
        self.message_builder = message_builder
        self.recall_provider = recall_provider

    async def analyze_input(self, input_text: str, *, max_tokens: Optional[int]) -> ContextAnalysis:
        segments = self.split_long_input(input_text, max_tokens=max_tokens)
        if len(segments) > self.config.summarize_max_segments:
            segments = segments[: self.config.summarize_max_segments]
        segment_tokens = [self.token_counter.count_text_tokens(s) for s in segments]
        requirement_indices = await self._select_requirement_segments_llm(segments)
        if not requirement_indices:
            requirement_indices = self._select_requirement_segments_heuristic(segments)
        requirement_text = "\n".join(segments[i] for i in requirement_indices if 0 <= i < len(segments))
        return ContextAnalysis(
            original_tokens=self.token_counter.count_text_tokens(input_text),
            segment_tokens=segment_tokens,
            segments=segments,
            requirement_indices=requirement_indices,
            requirement_text=requirement_text,
            background_summary=None,
            extraction=None,
        )

    async def classify_and_summarize(
        self,
        input_text: str,
        *,
        max_tokens: Optional[int],
        summarize_func: Optional[Any] = None,
    ) -> ContextProcessResult:
        analysis = await self.analyze_input(input_text, max_tokens=max_tokens)
        summarize_func = summarize_func or (lambda *_args, **_kwargs: "")
        background_summary = ""
        if len(analysis.segments) > 1:
            if callable(summarize_func):
                try:
                    background_summary = await summarize_func(
                        analysis.segments,
                        skip_indices=set(analysis.requirement_indices),
                    )
                except TypeError:
                    for idx, segment in enumerate(analysis.segments):
                        if idx in analysis.requirement_indices:
                            continue
                        background_summary = await summarize_func(
                            segment,
                            idx,
                            len(analysis.segments),
                            existing_summary=background_summary,
                        )
        extraction = await self.extract_requirements(analysis.requirement_text)
        analysis.background_summary = background_summary or None
        analysis.extraction = extraction
        normalized_input = self.build_normalized_input(
            analysis.requirement_text,
            analysis.background_summary,
            extraction,
        )
        return ContextProcessResult(
            analysis=analysis,
            normalized_input=normalized_input,
            requirement_text=analysis.requirement_text,
            background_summary=analysis.background_summary,
            extraction=extraction,
            segments=analysis.segments,
            requirement_segments=analysis.requirement_indices,
            summary=analysis.background_summary,
        )

    def split_long_input(self, text: str, *, max_tokens: Optional[int] = None) -> List[str]:
        if not text:
            return [text]

        if max_tokens is None:
            max_tokens = self.config.input_segment_max_tokens
        if max_tokens is None:
            max_tokens = max(1, int(self.token_counter.count_text_tokens(text)))
        if self.config.input_segment_max_tokens is not None:
            max_tokens = min(max_tokens, self.config.input_segment_max_tokens)

        text_tokens = self.token_counter.count_text_tokens(text)
        if text_tokens <= max_tokens:
            return [text]

        overlap_ratio = self.config.input_overlap_ratio
        overlap_tokens = max(0, int(max_tokens * overlap_ratio))

        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        sentence_split = re.compile(r"(?<=[。！？.!?])\s+")

        chunks: List[str] = []
        current: List[str] = []
        current_tokens = 0

        def flush_current() -> None:
            nonlocal current, current_tokens
            if current:
                chunks.append("".join(current).strip())
            current = []
            current_tokens = 0

        for para in paragraphs:
            sentences = sentence_split.split(para)
            for sent in sentences:
                if not sent:
                    continue
                sent_tokens = self.token_counter.count_text_tokens(sent)
                if current_tokens + sent_tokens <= max_tokens:
                    current.append(sent)
                    current_tokens += sent_tokens
                    continue

                flush_current()

                if sent_tokens <= max_tokens:
                    current.append(sent)
                    current_tokens = sent_tokens
                else:
                    step = max(1, int(len(sent) / max(1, int(sent_tokens / max_tokens))))
                    for i in range(0, len(sent), step):
                        part = sent[i:i + step]
                        if part.strip():
                            chunks.append(part)

        flush_current()

        if overlap_tokens and len(chunks) > 1:
            overlapped = []
            for idx, chunk in enumerate(chunks):
                if idx == 0:
                    overlapped.append(chunk)
                    continue
                prefix = chunks[idx - 1]
                prefix_tokens = self.token_counter.count_text_tokens(prefix)
                if prefix_tokens <= overlap_tokens:
                    carry = prefix
                else:
                    ratio = overlap_tokens / max(1, prefix_tokens)
                    tail_len = max(200, int(len(prefix) * ratio))
                    carry = prefix[-tail_len:]
                overlapped.append(carry + "\n" + chunk)
            chunks = overlapped

        return [c for c in chunks if c and c.strip()]

    def _select_requirement_segments_heuristic(self, segments: List[str]) -> List[int]:
        if not segments:
            return []
        keywords = [
            "请", "帮我", "需求", "目标", "想要", "希望", "问题是", "需要", "如何", "怎么办",
            "总结", "分析", "生成", "改写", "翻译", "提取", "整理", "输出", "给出",
        ]
        scores: List[int] = []
        for seg in segments:
            score = 0
            seg_str = seg.strip()
            for kw in keywords:
                if kw in seg_str:
                    score += seg_str.count(kw)
            if seg_str.startswith(("请", "帮我", "我需要", "需求", "目标")):
                score += 2
            scores.append(score)
        max_score = max(scores) if scores else 0
        if max_score <= 0:
            return [len(segments) - 1]
        threshold = max(1, int(max_score * 0.6))
        chosen = [i for i, s in enumerate(scores) if s >= threshold]
        return chosen or [scores.index(max_score)]

    async def _select_requirement_segments_llm(self, segments: List[str]) -> List[int]:
        cfg = self.config
        if not cfg.requirement_classifier_enabled or not self.llm:
            return []

        max_segments = max(1, int(cfg.requirement_classifier_max_segments))
        max_chars = max(200, int(cfg.requirement_classifier_max_chars))
        front_n = max(0, int(cfg.requirement_scan_front))
        back_n = max(0, int(cfg.requirement_scan_back))

        def score_segment(text: str) -> int:
            keywords = [
                "请", "帮我", "需求", "目标", "想要", "希望", "问题是", "需要", "如何", "怎么办",
                "总结", "分析", "生成", "改写", "翻译", "提取", "整理", "输出", "给出",
            ]
            score = 0
            for kw in keywords:
                if kw in text:
                    score += text.count(kw)
            if text.startswith(("请", "帮我", "我需要", "需求", "目标")):
                score += 2
            return score

        indexed = list(enumerate(segments))
        if len(indexed) > max_segments:
            scored = sorted(indexed, key=lambda x: score_segment(x[1]), reverse=True)
            chosen = set()
            for i in range(min(front_n, len(segments))):
                chosen.add(i)
            for i in range(max(0, len(segments) - back_n), len(segments)):
                chosen.add(i)
            for idx, _seg in scored:
                if len(chosen) >= max_segments:
                    break
                chosen.add(idx)
            indexed = [(i, segments[i]) for i in sorted(chosen)]

        items = []
        for idx, seg in indexed:
            seg_trim = seg.strip()
            if len(seg_trim) > max_chars:
                seg_trim = seg_trim[:max_chars]
            items.append({"index": idx, "text": seg_trim})

        system_prompt = cfg.requirement_classifier_prompt or REQUIREMENT_CLASSIFIER_PROMPT
        user_payload = {"segments": items}
        messages = self._build_messages(system_prompt, json.dumps(user_payload, ensure_ascii=False))
        try:
            response = await self.llm.agenerate(messages=messages, tools=None)
            raw = response.text.strip() if response else ""
            data = self._safe_json(raw)
            if not data:
                return []
            segments_data = data.get("segments", [])
            threshold = float(cfg.requirement_classifier_threshold)
            selected = [
                int(item.get("index"))
                for item in segments_data
                if item.get("label") == "requirement"
                and float(item.get("confidence", 0.0)) >= threshold
            ]
            return sorted(set(i for i in selected if 0 <= i < len(segments)))
        except Exception as e:
            logger.warning("requirement classifier failed: %s", e)
            return []

    async def extract_requirements(self, requirement_text: str) -> Optional[RequirementExtraction]:
        cfg = self.config
        if not cfg.requirement_extraction_enabled or not self.llm:
            return None
        max_chars = max(200, int(cfg.requirement_extraction_max_chars))
        text = requirement_text.strip()
        if len(text) > max_chars:
            text = text[:max_chars]

        system_prompt = cfg.requirement_extraction_prompt or REQUIREMENT_EXTRACTION_PROMPT
        messages = self._build_messages(system_prompt, text)
        try:
            response = await self.llm.agenerate(messages=messages, tools=None)
            raw = response.text.strip() if response else ""
            data = self._safe_json(raw)
            if not isinstance(data, dict):
                return None
            return RequirementExtraction.from_dict(data)
        except Exception as e:
            logger.warning("requirement extraction failed: %s", e)
            return None

    async def recall_with_summary(
        self,
        user_input: str,
        history: List[Dict[str, Any]],
        *,
        session_id: str,
        max_msgs: Optional[int] = None,
        max_chars: Optional[int] = None,
        llm: Any = None,
        session_memory: Optional[Dict[str, Any]] = None,
    ) -> RecallSummary:
        if not self.recall_provider:
            return RecallSummary(results=[], summary_text="")
        results = await self.recall_provider.search_with_history(
            user_input,
            history,
            session_id=session_id,
            max_msgs=max_msgs,
            max_chars=max_chars,
            llm=llm,
            session_memory=session_memory,
        )
        if not results:
            return RecallSummary(results=results, summary_text="")
        try:
            max_items = max(1, int(self.config.recall_summary_max_items))
            fmt = self.config.recall_summary_format or "- {session_id}: {count} matches (score={score:.2f})"
            lines = []
            for r in results[:max_items]:
                lines.append(
                    fmt.format(
                        session_id=getattr(r, "session_id", ""),
                        count=len(getattr(r, "messages", []) or []),
                        score=float(getattr(r, "score", 0.0)),
                    )
                )
            return RecallSummary(results=results, summary_text="\n".join(lines))
        except Exception:
            return RecallSummary(results=results, summary_text="")

    def summarize_recall_results(self, results: List[Any]) -> RecallSummary:
        if not results:
            return RecallSummary(results=[], summary_text="")
        try:
            max_items = max(1, int(self.config.recall_summary_max_items))
            fmt = self.config.recall_summary_format or "- {session_id}: {count} matches (score={score:.2f})"
            lines = []
            for r in results[:max_items]:
                lines.append(
                    fmt.format(
                        session_id=getattr(r, "session_id", ""),
                        count=len(getattr(r, "messages", []) or []),
                        score=float(getattr(r, "score", 0.0)),
                    )
                )
            return RecallSummary(results=results, summary_text="\n".join(lines))
        except Exception:
            return RecallSummary(results=results, summary_text="")

    def build_normalized_input(
        self,
        requirement_text: str,
        background_summary: Optional[str],
        extraction: Optional[RequirementExtraction],
    ) -> str:
        parts = []
        if extraction:
            parts.append("【真实需求】")
            if extraction.goal:
                parts.append(f"目标：{extraction.goal}")
            if extraction.scope:
                parts.append(f"资料范围：{extraction.scope}")
            if extraction.constraints:
                parts.append(f"约束：{extraction.constraints}")
            if extraction.output_format:
                parts.append(f"输出格式：{extraction.output_format}")
            if extraction.uncertainties:
                parts.append(f"不确定点：{extraction.uncertainties}")
        if requirement_text:
            parts.append("【用户原始需求】")
            parts.append(requirement_text)
        if background_summary:
            parts.append("【背景摘要】")
            parts.append(background_summary)
        return "\n".join(p for p in parts if p)

    def _build_messages(self, system_prompt: str, user_text: str) -> List[Any]:
        if self.message_builder:
            return self.message_builder(system_prompt, user_text)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

    @staticmethod
    def _safe_json(text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
        return None
