"""
Truncation Manager for Assistant

Central manager for context truncation and compaction.
适配 Assistant 的体系结构
"""

import asyncio
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime

from .token_counter import TokenCounter, create_token_counter
from .compaction import (
    MessageCompactor,
    CompactionConfig,
    CompactionResult,
    DEFAULT_COMPACTION_THRESHOLD,
)


logger = logging.getLogger(__name__)


@dataclass
class TruncationConfig:
    """Truncation configuration"""
    enabled: bool = True
    threshold: float = DEFAULT_COMPACTION_THRESHOLD  # 80% of context limit
    auto_compact: bool = True  # Automatically compact when threshold exceeded
    max_messages_before_compact: int = 50  # Hard limit
    keep_recent_messages: int = 5  # Keep N recent messages after compact
    check_interval: int = 5  # Check every N messages
    reserved_tokens: int = 4000  # Reserve for response
    input_overlap_ratio: float = 0.08  # Sliding window overlap
    input_segment_max_tokens: Optional[int] = None  # Hard cap for input segments
    requirement_classifier_enabled: bool = False
    requirement_classifier_threshold: float = 0.6
    requirement_classifier_max_segments: int = 8
    requirement_classifier_max_chars: int = 1200
    requirement_classifier_prompt: Optional[str] = None
    requirement_scan_front: int = 2
    requirement_scan_back: int = 2
    requirement_extraction_enabled: bool = False
    requirement_extraction_prompt: Optional[str] = None
    requirement_extraction_max_chars: int = 2000


@dataclass
class TruncationStats:
    """Statistics for truncation operations"""
    total_checks: int = 0
    total_compactions: int = 0
    total_tokens_saved: int = 0
    last_check_time: Optional[datetime] = None
    last_compact_time: Optional[datetime] = None
    avg_compaction_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "total_compactions": self.total_compactions,
            "total_tokens_saved": self.total_tokens_saved,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "last_compact_time": self.last_compact_time.isoformat() if self.last_compact_time else None,
            "avg_compaction_time_ms": self.avg_compaction_time_ms,
        }


class TruncationManager:
    """
    Manager for context truncation and compaction.

    Responsibilities:
    - Check if truncation is needed
    - Coordinate message compaction
    - Track truncation statistics
    - Provide truncation hooks for agent
    """

    def __init__(
        self,
        provider: Any,
        config: Optional[TruncationConfig] = None,
        token_counter: Optional[TokenCounter] = None,
        on_compaction_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_compaction_end: Optional[Callable[[CompactionResult], None]] = None,
    ):
        self.provider = provider
        self.config = config or TruncationConfig()
        self.token_counter = token_counter or create_token_counter()
        self.compactor = MessageCompactor(
            provider=provider,
            token_counter=self.token_counter,
            config=CompactionConfig(
                threshold=self.config.threshold,
                keep_recent_messages=self.config.keep_recent_messages,
            ),
        )

        self.on_compaction_start = on_compaction_start
        self.on_compaction_end = on_compaction_end

        self.stats = TruncationStats()
        self._message_count_since_check = 0
        self._lock = asyncio.Lock()

    def get_context_limit(self) -> int:
        """Get the context limit from provider"""
        if hasattr(self.provider, 'get_model_config'):
            config = self.provider.get_model_config()
            return getattr(config, 'context_limit', 128000)
        return 128000  # Default fallback

    def build_context_budget(
        self,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        budget = create_context_budget(
            provider=self.provider,
            system_prompt=system_prompt,
            tools=tools or [],
            token_counter=self.token_counter,
            reserved_for_response=self.config.reserved_tokens,
        )
        return {
            "limit": budget.total_limit,
            "available": budget.available_for_messages,
            "reserved": budget.reserved_for_response,
            "system_cost": budget.system_prompt_cost,
            "tools_cost": budget.tools_cost,
        }

    def split_long_input(
        self,
        text: str,
        max_chars: Optional[int],
        *,
        max_tokens: Optional[int] = None,
        overlap_ratio: Optional[float] = None,
    ) -> List[str]:
        """Token-aware split with sentence/paragraph preference and overlap."""
        if not text:
            return [text]

        if max_tokens is None:
            max_tokens = self.config.input_segment_max_tokens
        if max_tokens is None:
            if max_chars:
                max_tokens = max(1, int(max_chars / 4))
            else:
                max_tokens = max(1, int(self.token_counter.count_text_tokens(text)))
        if self.config.input_segment_max_tokens is not None:
            max_tokens = min(max_tokens, self.config.input_segment_max_tokens)
        text_tokens = self.token_counter.count_text_tokens(text)
        if (max_chars is None or len(text) <= max_chars) and text_tokens <= max_tokens:
            return [text]
        if overlap_ratio is None:
            overlap_ratio = self.config.input_overlap_ratio
        overlap_tokens = max(0, int(max_tokens * overlap_ratio))

        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        sentence_split = re.compile(r"(?<=[。！？.!?])\s+")

        chunks: List[str] = []
        current: List[str] = []
        current_tokens = 0

        def flush_current():
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

    def enforce_budget_on_conversation(
        self,
        conv: Any,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
        *,
        reserved_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Hard fallback: remove oldest messages and truncate last user message to fit budget."""
        from ..conversation import TextContent

        if reserved_tokens is None:
            reserved_tokens = self.config.reserved_tokens

        budget = self.build_context_budget(system_prompt, tools)
        limit = int(budget.get("limit", 0))
        available = int(budget.get("available", 0))
        target_limit = max(0, available)

        usage = self.estimate_context_usage(
            messages=conv.messages_to_dict(),
            tools=tools or [],
            system_prompt=system_prompt,
        )

        removed = 0
        while usage.get("total_tokens", 0) > target_limit and len(conv.messages) > 1:
            conv.messages.pop(0)
            removed += 1
            usage = self.estimate_context_usage(
                messages=conv.messages_to_dict(),
                tools=tools or [],
                system_prompt=system_prompt,
            )

        truncated_user = False
        if usage.get("total_tokens", 0) > target_limit and conv.messages:
            last_msg = conv.messages[-1]
            text_parts = []
            for c in last_msg.content:
                if isinstance(c, TextContent) and c.text:
                    text_parts.append(c.text)
            text = "\n".join(text_parts)
            if text:
                total_tokens = max(usage.get("total_tokens", 1), 1)
                ratio = max(0.1, min(1.0, target_limit / total_tokens))
                new_len = max(200, int(len(text) * ratio))
                truncated = text[:new_len].rstrip()
                if truncated != text:
                    for c in last_msg.content:
                        if isinstance(c, TextContent):
                            c.text = truncated
                            truncated_user = True
                            break
                usage = self.estimate_context_usage(
                    messages=conv.messages_to_dict(),
                    tools=tools or [],
                    system_prompt=system_prompt,
                )

        return {
            "removed": removed,
            "truncated_user": truncated_user,
            "usage": usage,
            "limit": limit,
            "available": available,
            "reserved": budget.get("reserved", reserved_tokens),
        }

    async def check_and_compact(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if compaction is needed and perform if necessary

        Returns:
            Tuple of (compaction_performed, usage_info)
        """
        if not self.config.enabled:
            return False, {"reason": "Truncation disabled"}

        async with self._lock:
            self.stats.total_checks += 1
            self.stats.last_check_time = datetime.now()

            context_limit = self.get_context_limit()

            # Check if we should check
            self._message_count_since_check += 1
            if self._message_count_since_check < self.config.check_interval:
                return False, {"reason": "Not due for check"}

            self._message_count_since_check = 0

            # Check if compaction is needed
            needs_compaction, usage_info = self.compactor.check_if_compaction_needed(
                messages, context_limit
            )

            if not needs_compaction:
                return False, usage_info

            # Check hard limit
            if len(messages) >= self.config.max_messages_before_compact:
                logger.warning(
                    f"Message count ({len(messages)}) exceeds hard limit "
                    f"({self.config.max_messages_before_compact}), forcing compaction"
                )

            # Perform compaction
            if self.config.auto_compact:
                return await self._perform_compaction(messages, system_prompt), usage_info

            return False, usage_info

    async def _perform_compaction(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
    ) -> bool:
        """Perform compaction and update stats"""
        start_time = datetime.now()

        # Notify start
        if self.on_compaction_start:
            self.on_compaction_start({
                "message_count": len(messages),
                "reason": "context_limit_exceeded",
            })

        try:
            result = await self.compactor.compact_messages(
                conversation_messages=messages,
                system_prompt=system_prompt,
                is_manual=False,
            )

            # Update stats
            self.stats.total_compactions += 1
            self.stats.total_tokens_saved += result.tokens_saved
            self.stats.last_compact_time = datetime.now()

            # Update average compaction time
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            avg = self.stats.avg_compaction_time_ms
            self.stats.avg_compaction_time_ms = (avg + elapsed) / 2

            logger.info(
                f"Compaction completed: {result.original_message_count} -> "
                f"{result.compacted_message_count} messages, "
                f"saved ~{result.tokens_saved} tokens"
            )

            # Notify end
            if self.on_compaction_end:
                self.on_compaction_end(result)

            return result.success

        except Exception as e:
            logger.exception(f"Compaction failed: {e}")
            return False

    def estimate_context_usage(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
    ) -> Dict[str, Any]:
        """Estimate current context usage"""
        context_limit = self.get_context_limit()

        return self.token_counter.estimate_context_usage(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            context_limit=context_limit,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get truncation statistics"""
        return self.stats.to_dict()

    def reset_stats(self) -> None:
        """Reset statistics"""
        self.stats = TruncationStats()

    def update_config(self, **kwargs) -> None:
        """Update configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        # Update compactor config
        self.compactor.config.threshold = self.config.threshold
        self.compactor.config.keep_recent_messages = self.config.keep_recent_messages

    def get_effective_limit(self) -> int:
        """Get effective context limit (before triggering compaction)"""
        return self.token_counter.get_effective_limit(
            self.get_context_limit(),
            self.config.threshold,
        )


async def create_truncation_manager(
    provider: Any,
    config: Optional[TruncationConfig] = None,
) -> TruncationManager:
    """Create a truncation manager"""
    return TruncationManager(provider, config)


@dataclass
class ContextBudget:
    """Context budget tracking"""
    total_limit: int
    system_prompt_cost: int = 0
    tools_cost: int = 0
    reserved_for_response: int = 4000  # Reserve for response

    @property
    def available_for_messages(self) -> int:
        """Available tokens for messages"""
        return max(
            0,
            self.total_limit
            - self.system_prompt_cost
            - self.tools_cost
            - self.reserved_for_response
        )

    def check(self, message_cost: int) -> Tuple[bool, int]:
        """Check if we have budget for message cost"""
        available = self.available_for_messages
        return message_cost <= available, available


def create_context_budget(
    provider: Any,
    system_prompt: str,
    tools: List[Dict[str, Any]],
    token_counter: TokenCounter,
    reserved_for_response: int = 4000,
) -> ContextBudget:
    """Create a context budget from provider and configuration"""
    context_limit = 128000  # Default

    if hasattr(provider, 'get_model_config'):
        config = provider.get_model_config()
        context_limit = getattr(config, 'context_limit', context_limit)

    system_cost = token_counter.count_text_tokens(system_prompt)
    tools_cost = 0
    if tools:
        tools_text = token_counter._tools_to_text(tools)
        tools_cost = token_counter.count_text_tokens(tools_text)

    return ContextBudget(
        total_limit=context_limit,
        system_prompt_cost=system_cost,
        tools_cost=tools_cost,
        reserved_for_response=reserved_for_response,
    )


__all__ = [
    "TruncationManager",
    "TruncationConfig",
    "TruncationStats",
    "ContextBudget",
    "create_truncation_manager",
    "create_context_budget",
]
