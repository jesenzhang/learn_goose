"""
Message Compaction for Context
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .token_counter import TokenCounter, create_token_counter

logger = logging.getLogger(__name__)

DEFAULT_COMPACTION_THRESHOLD = 0.8

CONVERSATION_CONTINUATION_TEXT = """The previous message contains a summary that was prepared because a context limit was reached.
Do not mention that you read a summary or that conversation summarization occurred.
Just continue the conversation naturally based on the summarized context."""


@dataclass
class CompactionConfig:
    threshold: float = DEFAULT_COMPACTION_THRESHOLD
    manual_compact: bool = False
    keep_recent_messages: int = 5


@dataclass
class CompactionResult:
    original_message_count: int
    compacted_message_count: int
    tokens_saved: int
    summary: str
    success: bool
    error: Optional[str] = None


class MessageCompactor:
    def __init__(
        self,
        llm: Any,
        *,
        token_counter: Optional[TokenCounter] = None,
        config: Optional[CompactionConfig] = None,
        message_builder: Optional[Any] = None,
    ):
        self.llm = llm
        self.token_counter = token_counter or create_token_counter()
        self.config = config or CompactionConfig()
        self.message_builder = message_builder

    def check_if_compaction_needed(
        self,
        conversation_messages: List[Dict[str, Any]],
        context_limit: int,
        current_token_count: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not context_limit:
            return False, {"reason": "Invalid context_limit"}
        if self.config.threshold <= 0.0 or self.config.threshold >= 1.0:
            return False, {"reason": "Compaction disabled by threshold"}
        if current_token_count is None:
            messages_text = self._messages_to_text(conversation_messages)
            current_token_count = self.token_counter.count_text_tokens(messages_text)
        usage_ratio = current_token_count / context_limit
        needs_compaction = usage_ratio > self.config.threshold
        usage_info = {
            "current_tokens": current_token_count,
            "context_limit": context_limit,
            "usage_percent": round(usage_ratio * 100, 2),
            "threshold_percent": round(self.config.threshold * 100, 2),
            "needs_compaction": needs_compaction,
        }
        return needs_compaction, usage_info

    async def compact_messages(
        self,
        conversation_messages: List[Dict[str, Any]],
        system_prompt: str,
    ) -> CompactionResult:
        original_count = len(conversation_messages)
        if original_count <= self.config.keep_recent_messages:
            return CompactionResult(
                original_message_count=original_count,
                compacted_message_count=original_count,
                tokens_saved=0,
                summary="No compaction needed",
                success=True,
            )
        try:
            messages_for_summarization = self._prepare_messages_for_summary(conversation_messages)
            summary = await self._generate_summary(system_prompt, messages_for_summarization)
            compacted = self._create_compacted_conversation(conversation_messages, summary)
            original_text = self._messages_to_text(conversation_messages)
            compacted_text = self._messages_to_text(compacted)
            tokens_saved = (
                self.token_counter.count_text_tokens(original_text) -
                self.token_counter.count_text_tokens(compacted_text)
            )
            return CompactionResult(
                original_message_count=original_count,
                compacted_message_count=len(compacted),
                tokens_saved=max(0, tokens_saved),
                summary=summary,
                success=True,
            )
        except Exception as e:
            logger.warning("Compaction failed: %s", e)
            return CompactionResult(
                original_message_count=original_count,
                compacted_message_count=original_count,
                tokens_saved=0,
                summary="",
                success=False,
                error=str(e),
            )

    def _prepare_messages_for_summary(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        prepared = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "text")
                        if block_type == "text":
                            text_parts.append(block.get("text", ""))
                        elif block_type == "tool_use":
                            tool_name = block.get("name", "unknown")
                            input_text = str(block.get("input", {}))
                            text_parts.append(f"[TOOL: {tool_name}] {input_text}")
                        elif block_type == "tool_result":
                            text_parts.append(f"[TOOL RESULT] {block.get('content', '')}")
                    else:
                        text_parts.append(str(content))
                content = "\n".join(text_parts)
            if len(content) > 2000:
                content = content[:2000] + "..."
            prepared.append({"role": role, "content": content})
        return prepared

    async def _generate_summary(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        messages_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
        prompt = (
            f"{system_prompt}\n\n"
            "The following is a conversation history that needs to be summarized due to context limits:\n\n"
            f"{messages_text}\n\n"
            "Please provide a concise summary of the key points, decisions, and current state of the conversation.\n"
            "Summary:"
        )
        if not self.llm:
            return self._simple_fallback_summary(messages)
        try:
            if self.message_builder:
                req = self.message_builder("Summarize the conversation", prompt)
                response = await self.llm.agenerate(messages=req, tools=None)
            else:
                response = await self.llm.agenerate(
                    messages=[{"role": "user", "content": prompt}],
                    tools=None,
                )
            return response.text.strip() if response else self._simple_fallback_summary(messages)
        except Exception:
            return self._simple_fallback_summary(messages)

    def _simple_fallback_summary(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "No conversation history."
        user_messages = [m for m in messages if m.get("role") == "user"]
        return f"Conversation with {len(user_messages)} user messages."

    def _create_compacted_conversation(
        self,
        original_messages: List[Dict[str, Any]],
        summary: str,
    ) -> List[Dict[str, Any]]:
        keep_count = self.config.keep_recent_messages
        recent_messages = original_messages[-keep_count:]
        compacted = []
        compacted.append({
            "role": "user",
            "content": f"[SUMMARY]\n{summary}\n[/SUMMARY]",
            "metadata": {
                "agent_visible": True,
                "user_visible": False,
                "is_summary": True,
            },
        })
        compacted.append({
            "role": "assistant",
            "content": CONVERSATION_CONTINUATION_TEXT,
            "metadata": {
                "agent_visible": True,
                "user_visible": False,
                "is_continuation": True,
            },
        })
        for msg in recent_messages:
            if "metadata" in msg:
                msg["metadata"] = dict(msg["metadata"])
                msg["metadata"]["agent_visible"] = False
            else:
                msg["metadata"] = {"agent_visible": False}
            compacted.append(msg)
        return compacted

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        text_parts.append(str(block.get("text", block)))
                    else:
                        text_parts.append(str(content))
                content = "\n".join(text_parts)
            parts.append(f"[{role}]: {content}")
        return "\n".join(parts)


__all__ = [
    "MessageCompactor",
    "CompactionConfig",
    "CompactionResult",
    "DEFAULT_COMPACTION_THRESHOLD",
]
