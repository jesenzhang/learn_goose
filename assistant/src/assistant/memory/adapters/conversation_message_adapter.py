"""
Conversation Message adapter for memory module.

Provides a MessageBuilder that uses assistant.conversation.Message.
"""

from __future__ import annotations

from typing import Any, List

from ...conversation import Message


def build_conversation_messages(system_prompt: str, user_content: str) -> List[Any]:
    return [Message.system(system_prompt), Message.user(user_content)]

