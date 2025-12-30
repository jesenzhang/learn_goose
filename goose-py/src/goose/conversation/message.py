import time
from enum import Enum
from typing import List, Optional, Any, Dict, Union, Literal
from pydantic import BaseModel, Field, ConfigDict

# --- 基础内容定义 ---
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"  # [新增] 必须添加，否则 OpenAI Provider 会报错

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    data: str
    mime_type: str = Field(alias="mimeType")

class RawContent(BaseModel):
    """工具返回的原始内容"""
    type: Literal["text", "image"] = "text"
    text: Optional[str] = None
    data: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")

# --- 工具调用 (Request) 相关 ---
class CallToolRequestParam(BaseModel):
    name: str
    arguments: Optional[Dict[str, Any]] = None

class ToolCall(BaseModel):
    """用于 Request：封装工具调用参数"""
    status: Literal["success", "error"] = "success"
    value: Optional[CallToolRequestParam] = None
    error: Optional[str] = None

    @classmethod
    def success(cls, req: CallToolRequestParam) -> "ToolCall":
        return cls(status="success", value=req)
    
    @classmethod
    def failure(cls, error: str) -> "ToolCall":
        return cls(status="error", error=error)

class ToolRequest(BaseModel):
    type: Literal["toolRequest"] = "toolRequest"
    id: str
    tool_call: ToolCall = Field(alias="toolCall")
    metadata: Optional[Dict[str, Any]] = None

# --- 工具结果 (Result) 相关 ---
class CallToolResult(BaseModel):
    """用于 Result：封装工具执行输出"""
    content: List[RawContent] = Field(default_factory=list)
    is_error: bool = Field(default=False, alias="isError")

    @classmethod
    def success(cls, content: List[RawContent]) -> "CallToolResult":
        return cls(content=content, is_error=False)

    @classmethod
    def failure(cls, error_message: str) -> "CallToolResult":
        return cls(
            content=[RawContent(type="text", text=error_message)],
            is_error=True
        )

class ToolResponse(BaseModel):
    type: Literal["toolResponse"] = "toolResponse"
    id: str
    # [关键] 这里直接持有 CallToolResult，不要再包一层 ToolCall
    tool_result: CallToolResult = Field(alias="toolResult")
    metadata: Optional[Dict[str, Any]] = None

# --- 其他内容定义 (保持不变) ---
class FrontendToolRequest(BaseModel):
    type: Literal["frontendToolRequest"] = "frontendToolRequest"
    id: str
    tool_call: ToolCall = Field(alias="toolCall")

class ToolConfirmationRequest(BaseModel):
    type: Literal["toolConfirmationRequest"] = "toolConfirmationRequest"
    id: str
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")

class ActionRequiredData(BaseModel):
    type: str 
    tool_name: Optional[str] = Field(None, alias="toolName")
    tool_call_id: Optional[str] = Field(None, alias="toolCallId")
    message: Optional[str] = None
    id: Optional[str] = None

class ActionRequired(BaseModel):
    type: Literal["actionRequired"] = "actionRequired"
    data: ActionRequiredData

class ThinkingContent(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None

class RedactedThinkingContent(BaseModel):
    type: Literal["redactedThinking"] = "redactedThinking"

class SystemNotificationType(str, Enum):
    THINKING = "thinkingMessage"
    INLINE = "inlineMessage"

class SystemNotification(BaseModel):
    type: Literal["systemNotification"] = "systemNotification"
    notification_type: SystemNotificationType = Field(alias="notificationType")
    msg: str

# --- 消息聚合 ---
MessageContent = Union[
    TextContent, ImageContent, ToolRequest, ToolResponse,
    FrontendToolRequest, ToolConfirmationRequest, ActionRequired,
    ThinkingContent, RedactedThinkingContent, SystemNotification
]

class MessageMetadata(BaseModel):
    user_visible: bool = Field(default=True, alias="userVisible")
    agent_visible: bool = Field(default=True, alias="agentVisible")
    model_config = ConfigDict(populate_by_name=True) # 允许使用 snake_case 初始化

    @classmethod
    def invisible(cls) -> "MessageMetadata":
        return cls(userVisible=False, agentVisible=False)

class Message(BaseModel):
    id: Optional[str] = None
    role: Role
    created: int = Field(default_factory=lambda: int(time.time()))
    content: List[MessageContent] = Field(default_factory=list)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def system(cls, text: str = "") -> "Message":
        msg = cls(role=Role.SYSTEM)
        if text:
            msg.content.append(TextContent(text=text))
        return msg

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

    @classmethod
    def tool(cls, text: str = "", tool_call_id: str = "") -> "Message":
        msg = cls(role=Role.TOOL)
        if text:
            msg.content.append(ToolResponse(id=tool_call_id, content=[RawContent(text=text)]))
        return msg

    def with_text(self, text: str) -> "Message":
        self.content.append(TextContent(text=text))
        return self

    def with_tool_request(self, id: str, name: str, args: Dict[str, Any]) -> "Message":
        req = CallToolRequestParam(name=name, arguments=args)
        self.content.append(ToolRequest(
            id=id, 
            toolCall=ToolCall.success(req)
        ))
        return self

    def with_tool_response(self, id: str, output: str) -> "Message":
        res = CallToolResult(content=[RawContent(text=output)])
        self.content.append(ToolResponse(
            id=id,
            toolResult=res # 直接传递 CallToolResult，不要包 ToolCall.success
        ))
        return self

    def as_concat_text(self) -> str:
        return "\n".join([c.text for c in self.content if isinstance(c, TextContent)])