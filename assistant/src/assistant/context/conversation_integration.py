"""
Context integration for Conversation

Provides helpers needed by context budget/compaction without relying on truncation module.
"""

import logging
from typing import Any, Dict, List, Optional

from .interfaces import TruncationProvider

logger = logging.getLogger(__name__)


class ConversationContextMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._truncation_provider: Optional[TruncationProvider] = None
        self._last_compaction_summary: Optional[str] = None

    def set_truncation_provider(self, provider: TruncationProvider):
        self._truncation_provider = provider

    def get_truncation_provider(self) -> Optional[TruncationProvider]:
        return self._truncation_provider

    def messages_to_dict(self) -> List[Dict[str, Any]]:
        result = []
        all_messages = []
        if hasattr(self, "_ephemeral_messages"):
            all_messages.extend(self._ephemeral_messages)
        if hasattr(self, "messages"):
            all_messages.extend(self.messages)
        for msg in all_messages:
            msg_dict = {
                "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                "content": []
            }
            for content in msg.content:
                if hasattr(content, "model_dump"):
                    msg_dict["content"].append(content.model_dump())
                else:
                    msg_dict["content"].append(str(content))
            result.append(msg_dict)
        return result

    def apply_compaction(self, compacted_messages: List[Dict[str, Any]]):
        self.messages.clear()
        try:
            from ..conversation import Message, Role
            from ..conversation.message import TextContent, MessageVisible
            for msg_dict in compacted_messages:
                role_str = msg_dict.get("role", "user")
                if isinstance(role_str, str):
                    if role_str == "system":
                        role = Role.SYSTEM
                    elif role_str == "assistant":
                        role = Role.ASSISTANT
                    elif role_str == "user":
                        role = Role.USER
                    else:
                        role = Role.USER
                else:
                    role = role_str
                content_list = []
                content = msg_dict.get("content", "")
                if isinstance(content, str):
                    content_list.append(TextContent(text=content))
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict):
                            if c.get("type") == "text":
                                content_list.append(TextContent(text=c.get("text", "")))
                            else:
                                content_list.append(TextContent(text=str(c)))
                        else:
                            content_list.append(TextContent(text=str(c)))
                else:
                    content_list.append(TextContent(text=str(content)))
                metadata = msg_dict.get("metadata", {}) or {}
                message = Message(role=role, content=content_list)
                if metadata:
                    message.metadata = dict(metadata)
                if metadata:
                    if "agent_visible" in metadata or "user_visible" in metadata:
                        message.visible = MessageVisible(
                            agent_visible=metadata.get("agent_visible", True),
                            user_visible=metadata.get("user_visible", True),
                        )
                self.messages.append(message)
        except Exception as e:
            logger.error("Failed to apply compaction: %s", e, exc_info=True)

    def set_last_compaction_summary(self, summary: str) -> None:
        self._last_compaction_summary = summary

    def get_last_compaction_summary(self) -> Optional[str]:
        return self._last_compaction_summary


__all__ = ["ConversationContextMixin"]
