# 这相当于 Rust 的: pub use message::Message;
from .message import (
    Message, 
    MessageContent, 
    Role, 
    MessageMetadata,
    TextContent,
    ToolRequest,
    ToolResponse,
    ImageContent,
    ToolCallResult,
    ToolResultContent,
    CallToolResult,
    CallToolRequestParam
)

# 这相当于 Rust 的: pub use conversation::Conversation;
from .conversation import (
    Conversation, 
    fix_conversation
)

# 定义当使用 from conversation import * 时导出哪些内容
__all__ = [
    "Message",
    "MessageContent",
    "Role",
    "MessageMetadata",
    "TextContent",
    "ToolRequest",
    "ToolResponse",
    "Conversation",
    "fix_conversation",
    "ImageContent",
    "ToolCallResult",
    "ToolResultContent",
    "CallToolResult",
    "CallToolRequestParam"
]