# goose-py/conversation/message.py
from __future__ import annotations
import time
from enum import Enum
from typing import List, Optional, Any, Dict, Union, Literal, Generic, TypeVar
from pydantic import BaseModel, Field, field_validator

# --- 基础枚举 ---

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

# --- Tool Result 泛型封装 (对应 ToolCallResult) ---

T = TypeVar('T')

class ToolCallResult(BaseModel, Generic[T]):
    """
    对应 Rust: ToolCallResult<T>
    序列化格式: { "status": "success", "value": T } 或 { "status": "error", "error": "..." }
    """
    status: Literal["success", "error"]
    value: Optional[T] = None
    error: Optional[str] = None

    @classmethod
    def success(cls, value: T) -> "ToolCallResult[T]":
        return cls(status="success", value=value)

    @classmethod
    def failure(cls, error: str) -> "ToolCallResult[T]":
        return cls(status="error", error=error)

# --- 具体的数据载荷定义 ---

class CallToolRequestParam(BaseModel):
    name: str
    arguments: Optional[Dict[str, Any]] = None

class ToolResultContent(BaseModel):
    type: Literal["text", "image"] = "text"
    text: Optional[str] = None
    data: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")

class CallToolResult(BaseModel):
    content: List[ToolResultContent] = Field(default_factory=list)
    is_error: bool = Field(default=False, alias="isError")

# --- Message Content Variants ---

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    data: str
    mime_type: str = Field(alias="mimeType")

class ToolRequest(BaseModel):
    """对应 Rust: ToolRequest"""
    type: Literal["toolRequest"] = "toolRequest"
    id: str
    tool_call: ToolCallResult[CallToolRequestParam] = Field(alias="toolCall")
    metadata: Optional[Dict[str, Any]] = None

class ToolResponse(BaseModel):
    """对应 Rust: ToolResponse"""
    type: Literal["toolResponse"] = "toolResponse"
    id: str
    tool_result: ToolCallResult[CallToolResult] = Field(alias="toolResult")
    metadata: Optional[Dict[str, Any]] = None

class ActionRequiredData(BaseModel):
    actionType: str # "toolConfirmation" | "elicitation" | ...
    id: Optional[str] = None
    tool_name: Optional[str] = Field(None, alias="toolName")
    arguments: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None

class ActionRequired(BaseModel):
    type: Literal["actionRequired"] = "actionRequired"
    data: ActionRequiredData

class ThinkingContent(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str

class RedactedThinkingContent(BaseModel):
    type: Literal["redactedThinking"] = "redactedThinking"
    data: str

class SystemNotificationType(str, Enum):
    THINKING = "thinkingMessage"
    INLINE = "inlineMessage"

class SystemNotification(BaseModel):
    type: Literal["systemNotification"] = "systemNotification"
    notification_type: SystemNotificationType = Field(alias="notificationType")
    msg: str

class FrontendToolRequest(BaseModel):
    type: Literal["frontendToolRequest"] = "frontendToolRequest"
    id: str
    tool_call: ToolCallResult[CallToolRequestParam] = Field(alias="toolCall")

# --- 联合类型 ---

MessageContent = Union[
    TextContent,
    ImageContent,
    ToolRequest,
    ToolResponse,
    ActionRequired,
    ThinkingContent,
    RedactedThinkingContent,
    SystemNotification,
    FrontendToolRequest
]

# --- Message Metadata & Body ---

class MessageMetadata(BaseModel):
    user_visible: bool = Field(default=True, alias="userVisible")
    agent_visible: bool = Field(default=True, alias="agentVisible")

    @classmethod
    def invisible(cls) -> "MessageMetadata":
        """完全不可见 (通常用于被标记删除的消息)"""
        return cls(userVisible=False, agentVisible=False)

    @classmethod
    def agent_only(cls) -> "MessageMetadata":
        """
        仅 Agent 可见
        场景：System Prompt、压缩后的总结 (Summary)、思维链 (Thinking)
        """
        return cls(userVisible=False, agentVisible=True)

    def with_agent_invisible(self) -> "MessageMetadata":
        """
        返回一个副本，并将 Agent 可见性设为 False。
        场景：压缩后，旧的详细消息对 Agent 隐藏，但对用户历史记录保留可见。
        """
        # Pydantic v2 使用 model_copy
        return self.model_copy(update={"agent_visible": False})

class Message(BaseModel):
    id: Optional[str] = None
    role: Role
    created: int = Field(default_factory=lambda: int(time.time()))
    content: List[MessageContent] = Field(default_factory=list)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)

    # --- Helpers ---
    
    @classmethod
    def user(cls, text: str = "") -> "Message":
        msg = cls(role=Role.USER)
        if text:
            msg.content.append(TextContent(text=text))
        return msg

    @classmethod
    def assistant(cls, text: str = "") -> "Message":
        msg = cls(role=Role.ASSISTANT)
        if text:
            msg.content.append(TextContent(text=text))
        return msg

    def with_text(self, text: str) -> "Message":
        self.content.append(TextContent(text=text))
        return self

    def with_tool_request(self, id: str, name: str, args: Dict[str, Any]) -> "Message":
        req = CallToolRequestParam(name=name, arguments=args)
        self.content.append(ToolRequest(
            id=id, 
            toolCall=ToolCallResult.success(req)
        ))
        return self

    def with_tool_response(self, id: str, output: str) -> "Message":
        res = CallToolResult(content=[ToolResultContent(text=output)])
        self.content.append(ToolResponse(
            id=id,
            toolResult=ToolCallResult.success(res)
        ))
        return self

    def with_metadata(self, metadata: MessageMetadata) -> "Message":
        """
        链式更新 Metadata
        用法: msg.with_metadata(MessageMetadata.agent_only())
        """
        # 使用 model_copy 创建副本，保证不可变性 (Immutable style)
        return self.model_copy(update={"metadata": metadata})

    def is_agent_visible(self) -> bool:
        """Helper: 检查 Agent 是否可见"""
        return self.metadata.agent_visible
    
    def as_concat_text(self) -> str:
        return "\n".join([c.text for c in self.content if isinstance(c, TextContent)])