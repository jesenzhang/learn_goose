import asyncio
import logging
from typing import Any, Dict, Optional, List

from .compaction import MessageCompactor, CompactionConfig
from .config import ContextConfig
from .interfaces import TruncationProvider
from .models import TruncationResult
from .token_counter import TokenCounter, create_token_counter

logger = logging.getLogger(__name__)


class DefaultTruncationProvider(TruncationProvider):
    def __init__(
        self,
        *,
        llm: Any,
        config: ContextConfig,
        token_counter: Optional[TokenCounter] = None,
        message_builder: Optional[Any] = None,
        context_limit: Optional[int] = None,
    ) -> None:
        self.config = config
        self.token_counter = token_counter or create_token_counter()
        self.context_limit = context_limit
        self.compactor = MessageCompactor(
            llm,
            token_counter=self.token_counter,
            config=CompactionConfig(
                threshold=config.threshold,
                keep_recent_messages=config.keep_recent_messages,
            ),
            message_builder=message_builder,
        )
        self._message_count_since_check = 0
        self._lock = asyncio.Lock()

    def build_context_budget(self, system_prompt: str, tools: Optional[List[Dict[str, Any]]] = None):
        return {}

    async def check_and_apply_truncation(
        self,
        conversation: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> TruncationResult:
        if not self.config.auto_compact:
            return TruncationResult(truncated=False)
        if not self.context_limit:
            return TruncationResult(truncated=False)

        messages_dict = conversation.messages_to_dict() if hasattr(conversation, "messages_to_dict") else []
        async with self._lock:
            self._message_count_since_check += 1
            if self._message_count_since_check < self.config.check_interval:
                return TruncationResult(truncated=False, usage={"reason": "Not due for check"})
            self._message_count_since_check = 0
            needs_compaction, usage_info = self.compactor.check_if_compaction_needed(
                messages_dict,
                self.context_limit,
            )
            if not needs_compaction and len(messages_dict) < self.config.max_messages_before_compact:
                return TruncationResult(truncated=False, usage=usage_info)

            result = await self.compactor.compact_messages(
                conversation_messages=messages_dict,
                system_prompt=system_prompt,
            )
            if result.success and result.compacted_message_count < len(messages_dict):
                compacted_messages = self.compactor._create_compacted_conversation(
                    messages_dict,
                    result.summary,
                )
                if hasattr(conversation, "apply_compaction"):
                    conversation.apply_compaction(compacted_messages)
                if hasattr(conversation, "set_last_compaction_summary"):
                    conversation.set_last_compaction_summary(result.summary)
                return TruncationResult(
                    truncated=True,
                    summary_text=result.summary,
                    usage=usage_info,
                )
            return TruncationResult(truncated=False, usage=usage_info)

    def enforce_budget_on_conversation(
        self,
        conversation: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> TruncationResult:
        return TruncationResult(truncated=False)


__all__ = ["DefaultTruncationProvider"]
