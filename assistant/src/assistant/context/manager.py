from typing import Any, Dict, List, Optional
import hashlib
import json
import time

from .budget import ContextBudgeter
from .builder import ContextBuilder
from .cache import LRUCache
from .config import ContextConfig
from .compressor import ContextCompressor
from .interfaces import LLMClient, RecallProvider, TokenCounter, TruncationProvider, SessionMemoryProvider
from .metrics import ContextTracer
from .models import (
    ContextAnalysis,
    ContextPayload,
    ContextProcessResult,
    RecallBundle,
    RecallSummary,
    RequirementExtraction,
    TruncationResult,
)
from .recall import ContextRecall
from .rewrite import QueryRewriter
from .truncator import ContextTruncator
from .window_manager import WindowManager


class ContextManager:
    def __init__(
        self,
        *,
        config: ContextConfig,
        token_counter: TokenCounter,
        llm: Optional[LLMClient] = None,
        message_builder: Optional[Any] = None,
        truncation_provider: Optional[TruncationProvider] = None,
        recall_provider: Optional[RecallProvider] = None,
        rerank_provider: Optional[Any] = None,
        session_memory_provider: Optional[SessionMemoryProvider] = None,
    ) -> None:
        self.config = config
        self.token_counter = token_counter
        self.builder = ContextBuilder(
            config=config,
            token_counter=token_counter,
            llm=llm,
            message_builder=message_builder,
            recall_provider=recall_provider,
        )
        self.budgeter = ContextBudgeter(token_counter)
        self.compressor = ContextCompressor(llm, message_builder or self._default_message_builder)
        self.truncator = ContextTruncator(
            truncation_provider,
            token_counter=token_counter,
            budgeter=self.budgeter,
            context_limit=self.config.context_limit,
            reserved_tokens=self.config.reserved_tokens,
        )
        self.window_manager = WindowManager(keep_recent_messages=config.keep_recent_messages)
        self.truncation_provider = truncation_provider
       
        self.recaller = ContextRecall(config, recall_provider=recall_provider, rerank_provider=rerank_provider)
        self.rewriter = QueryRewriter(config, message_builder=message_builder)
        self.session_memory_provider = session_memory_provider
        self.tracer = ContextTracer() if config.metrics_enabled else None
        self.cache = LRUCache(config.cache_size, config.cache_ttl_seconds) if config.cache_enabled else None

    async def classify_and_summarize(
        self,
        input_text: str,
        *,
        max_tokens: Optional[int],
        summarize_func: Optional[Any] = None,
    ) -> ContextProcessResult:
        start = time.monotonic()
        result = await self.builder.classify_and_summarize(
            input_text,
            max_tokens=max_tokens,
            summarize_func=summarize_func or (
                lambda segments, skip_indices: self.compressor.summarize_segments(
                    segments,
                    skip_indices=skip_indices,
                    max_concurrency=self.config.summarize_max_concurrency,
                    fuse=self.config.summarize_fuse_enabled,
                    fuse_max_chars=self.config.summarize_fuse_max_chars,
                    fallback_strategy=self.config.summarize_fallback_strategy,
                    fallback_max_chars=self.config.summarize_fallback_max_chars,
                    fallback_max_segments=self.config.summarize_fallback_max_segments,
                )
            ),
        )
        if self.tracer and isinstance(result.analysis, ContextAnalysis):
            analysis = result.analysis
            self.tracer.set_tokens(original=analysis.original_tokens)
            self.tracer.set_segments(len(analysis.segments))
            if analysis.background_summary:
                self.tracer.set_summary_tokens(self.token_counter.count_text_tokens(analysis.background_summary))
            if self.compressor.last_fallback_used:
                self.tracer.set_summary_fallback(True)
            self.tracer.mark("classify_and_summarize_ms", int((time.monotonic() - start) * 1000))
        return result

    async def analyze_input(
        self,
        input_text: str,
        *,
        max_tokens: Optional[int],
    ) -> ContextAnalysis:
        return await self.builder.analyze_input(input_text, max_tokens=max_tokens)

    def build_context_budget(self, system_prompt: str, tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        if not self.config.context_limit:
            return {}
        return self.budgeter.build(
            context_limit=int(self.config.context_limit),
            reserved_tokens=int(self.config.reserved_tokens),
            system_prompt=system_prompt,
            tools=tools or [],
        )

    async def check_and_apply_truncation(
        self,
        conv: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> bool:
        result = await self.truncator.check_and_apply_truncation(
            conv,
            system_prompt=system_prompt,
            tools=tools,
        )
        if self.tracer:
            dropped = 0
            if isinstance(result.usage, dict):
                dropped = int(result.usage.get("removed", 0) or 0)
            self.tracer.set_truncation(result.truncated, dropped_messages=dropped)
        return result.truncated

    async def apply_truncation(
        self,
        conv: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> TruncationResult:
        result = await self.truncator.check_and_apply_truncation(
            conv,
            system_prompt=system_prompt,
            tools=tools,
        )
        if self.tracer:
            dropped = 0
            if isinstance(result.usage, dict):
                dropped = int(result.usage.get("removed", 0) or 0)
            self.tracer.set_truncation(result.truncated, dropped_messages=dropped)
        return result

    def enforce_budget_on_conversation(
        self,
        conv: Any,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> TruncationResult:
        result = self.truncator.enforce_budget_on_conversation(
            conv,
            system_prompt,
            tools,
        )
        if self.tracer and isinstance(result.usage, dict):
            self.tracer.set_budget(
                context_limit=int(result.usage.get("limit", 0) or 0),
                reserved_tokens=int(result.usage.get("reserved", 0) or 0),
                available_tokens=int(result.usage.get("available", 0) or 0),
                total_tokens=int((result.usage.get("usage") or {}).get("total_tokens", 0) or 0),
            )
            self.tracer.set_truncation(result.truncated, dropped_messages=int(result.usage.get("removed", 0) or 0))
        return result

    def build_normalized_input(
        self,
        requirement_text: str,
        background_summary: Optional[str],
        extraction: Optional[RequirementExtraction],
    ) -> str:
        return self.builder.build_normalized_input(requirement_text, background_summary, extraction)

    def update_compaction_boundary(self, state: Any, conv: Any) -> None:
        """Record compaction boundary based on current conversation messages."""
        first_kept = None
        for msg in getattr(conv, "messages", []):
            meta = getattr(msg, "metadata", None) or {}
            if meta.get("is_summary") or meta.get("is_continuation"):
                continue
            first_kept = getattr(msg, "id", None)
            break
        if first_kept:
            setattr(state, "compacted_until_message_id", first_kept)

    def ensure_compressed_context_message(self, state: Any, conv: Any) -> None:
        """Inject compressed context into ephemeral messages."""
        summary = getattr(state, "compressed_context", None)
        if not summary or not hasattr(conv, "_ephemeral_messages"):
            return
        existing = []
        for msg in conv._ephemeral_messages:
            meta = getattr(msg, "metadata", None) or {}
            if meta.get("is_compacted_context"):
                existing.append(msg)
        if existing and existing[-1].metadata.get("compressed_context") == summary:
            return
        if existing:
            conv._ephemeral_messages = [
                msg for msg in conv._ephemeral_messages
                if not (getattr(msg, "metadata", None) or {}).get("is_compacted_context")
            ]
        try:
            from ..conversation import Message
            ctx_msg = Message.user(summary).with_visibility(user_visible=False, agent_visible=True)
            ctx_msg.metadata = {
                "is_compacted_context": True,
                "compressed_context": summary,
            }
            conv.push(ctx_msg, ephemeral=True)
        except Exception:
            return

    def ensure_context_payload_message(self, state: Any, conv: Any, payload: ContextPayload) -> None:
        """Inject context payload summary into ephemeral messages."""
        if not payload or not hasattr(conv, "_ephemeral_messages"):
            return
        if not payload.recall_summary:
            return
        existing = []
        for msg in conv._ephemeral_messages:
            meta = getattr(msg, "metadata", None) or {}
            if meta.get("is_context_payload"):
                existing.append(msg)
        if existing and existing[-1].metadata.get("recall_summary") == payload.recall_summary:
            return
        if existing:
            conv._ephemeral_messages = [
                msg for msg in conv._ephemeral_messages
                if not (getattr(msg, "metadata", None) or {}).get("is_context_payload")
            ]
        try:
            from ..conversation import Message
            text = f"Context Recall Summary:\n{payload.recall_summary}"
            ctx_msg = Message.system(text).with_visibility(user_visible=False, agent_visible=True)
            ctx_msg.metadata = {
                "is_context_payload": True,
                "recall_summary": payload.recall_summary,
            }
            conv.push(ctx_msg, ephemeral=True)
        except Exception:
            return

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
        return await self.builder.recall_with_summary(
            user_input,
            history,
            session_id=session_id,
            max_msgs=max_msgs,
            max_chars=max_chars,
            llm=llm,
            session_memory=session_memory,
        )

    async def recall_and_rewrite(
        self,
        query: str,
        history: List[Dict[str, Any]],
        *,
        session_id: str,
        user_id: Optional[int] = None,
        run_id: Optional[str] = None,
        llm: Any = None,
        session_memory: Optional[Dict[str, Any]] = None,
    ) -> RecallBundle:
        if session_memory is None and self.session_memory_provider:
            try:
                session_memory = await self.session_memory_provider.load_session_memory(session_id)
            except Exception:
                session_memory = None
        cache_key = None
        if self.cache:
            history_fingerprint = ""
            try:
                history_dump = json.dumps(history, ensure_ascii=False, sort_keys=True)
                history_fingerprint = hashlib.md5(history_dump[:4000].encode("utf-8")).hexdigest()
            except Exception:
                history_fingerprint = f"len:{len(history)}"
            digest = hashlib.md5(
                f"{session_id}:{user_id}:{run_id}:{query}:{history_fingerprint}".encode("utf-8")
            ).hexdigest()
            cache_key = f"recall:{digest}"
            cached = self.cache.get(cache_key)
            if cached:
                if self.tracer:
                    self.tracer.set_cache_hit(True)
                return cached
            if self.tracer:
                self.tracer.set_cache_hit(False)
        start = time.monotonic()
        rewritten = await self.rewriter.rewrite(
            user_input=query,
            history=history,
            session_memory=session_memory,
            llm=llm,
        )
        if self.tracer:
            self.tracer.set_rewrite_used(bool(rewritten and rewritten != query))
        results = await self.recaller.recall(
            user_input=rewritten,
            history=history,
            session_id=session_id,
            llm=llm,
            session_memory=session_memory,
        )
        if self.tracer:
            self.tracer.set_recall_count(len(results))
        summary = self.builder.summarize_recall_results(results)
        if self.tracer:
            self.tracer.mark("recall_and_rewrite_ms", int((time.monotonic() - start) * 1000))
        bundle = RecallBundle(query=query, rewritten_query=rewritten, summary=summary)
        if self.cache and cache_key:
            self.cache.set(cache_key, bundle)
        return bundle

    def get_metrics(self) -> Optional[Dict[str, Any]]:
        if not self.tracer:
            return None
        return self.tracer.metrics.__dict__.copy()

    def build_context(
        self,
        *,
        normalized_input: str,
        compressed_context: Optional[str],
        recall_summary: Optional[str],
        recent_history: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextPayload:
        return ContextPayload(
            input_text=normalized_input,
            compressed_context=compressed_context,
            recall_summary=recall_summary,
            recent_history=recent_history,
            metadata=metadata or {},
        )

    @staticmethod
    def _default_message_builder(system_prompt: str, user_text: str) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
