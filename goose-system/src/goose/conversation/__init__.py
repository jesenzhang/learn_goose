"""
Conversation Module Init

Conversation 模块初始化
参考 goose-rs crates/goose/src/conversation/message.rs 实现
使用 Pydantic 实现
"""

from .message import (
    Conversation,
    Message,
    Role,
    MessageContent,
    MessageMetadata,
    SystemNotificationType,
    ActionType,
    TextContent,
    ImageContent,
    ToolRequestContent,
    ToolResponseContent,
    ToolConfirmationRequestContent,
    ActionRequiredContent,
    ThinkingContent,
    RedactedThinkingContent,
    FrontendToolRequestContent,
    SystemNotificationContent,
    ActionRequiredElicitation,
    ActionRequiredElicitationResponse,
)

__all__ = [
    "Conversation",
    "Message",
    "Role",
    "MessageContent",
    "MessageMetadata",
    "SystemNotificationType",
    "ActionType",
    "TextContent",
    "ImageContent",
    "ToolRequestContent",
    "ToolResponseContent",
    "ToolConfirmationRequestContent",
    "ActionRequiredContent",
    "ThinkingContent",
    "RedactedThinkingContent",
    "FrontendToolRequestContent",
    "SystemNotificationContent",
    "ActionRequiredElicitation",
    "ActionRequiredElicitationResponse",
]
