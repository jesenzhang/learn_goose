import time
import json
from enum import Enum
from typing import List, Optional, Any, Dict, Union, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
import uuid

# --- 基础内容定义 ---
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class TextContent(BaseModel):
    type: str = "text"
    text: str

class ImageContent(BaseModel):
    type: str = "image"
    data: str
    mime_type: str = Field(alias="mimeType")
    
    # [FIX] 允许 mime_type 或 mimeType
    model_config = ConfigDict(populate_by_name=True)

class RawContent(BaseModel):
    """工具返回的原始内容"""
    type: str = "text"
    text: Optional[str] = None
    data: Optional[Any] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")
    
    # 3. Artifact 增强信息 [NEW]
    title: Optional[str] = None       # Artifact 标题 (e.g., "2024年销售报表")
    id: Optional[str] = None          # Artifact ID (用于后续引用或交互)
    metadata: Optional[Dict[str, Any]] = None # 元数据 (e.g., source, timestamp, confidence)
    
    # [FIX] 允许 mime_type 或 mimeType
    model_config = ConfigDict(populate_by_name=True)

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

    def is_error(self) -> bool:
        return self.status == "error"
    
class ToolRequest(BaseModel):
    type: str = "toolRequest"
    id: str
    tool_call: ToolCall = Field(alias="toolCall")
    metadata: Optional[Dict[str, Any]] = None

    # [FIX] 关键修复：允许数据库中的 tool_call 字段被正确映射
    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    @classmethod
    def validate_tool_call(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 兼容 toolCall (前端) 和 tool_call (后端/DB)
            tool_call_value = data.get('toolCall') or data.get('tool_call')
            if tool_call_value is None:
                data['toolCall'] = ToolCall.failure("Missing tool call data")
        return data
    

# --- 工具结果 (Result) 相关 ---
class CallToolResult(BaseModel):
    """用于 Result：封装工具执行输出"""
    content: List[RawContent] = Field(default_factory=list)
    is_error: bool = Field(default=False, alias="isError")

    metadata: Optional[Dict[str, Any]] = None

    # [FIX] 允许 is_error 或 isError
    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def success(cls, content: List[RawContent]) -> "CallToolResult":
        return cls(content=content, is_error=False)

    @classmethod
    def failure(cls, error_message: str) -> "CallToolResult":
        return cls(
            content=[RawContent(type="text", text=error_message)],
            is_error=True
        )
    
    @classmethod
    def from_text(cls, text: str):
        return cls(content=[RawContent(type="text", text=text)])
    
    @classmethod
    def from_artifact(cls, view: str, data: Any, type="dataset", title: str = None, id: str = None, metadata: Dict = None):
        """
        [NEW] 快速构造 Artifact 结果的辅助方法
        
        Args:
            view (str): 给 LLM 看的文本摘要/Markdown。
            data (Any): 给前端渲染用的完整数据。
            type (str): Artifact 类型 (e.g., 'table', 'chart', 'recommendation_list')。
            title (str): 标题。
            metadata (Dict): 额外元数据。
        """
        # 如果没有指定文本，默认使用 JSON 字符串 (作为兜底)
        text_representation = view
        
        return cls(content=[
            RawContent(
                type=type, 
                text=text_representation, 
                data=data, 
                title=title,
                id=id,
                metadata=metadata
            )
        ])
        
class ToolResponse(BaseModel):
    type: str = "toolResponse"
    id: str
    tool_result: CallToolResult = Field(alias="toolResult")
    metadata: Optional[Dict[str, Any]] = None

    # [FIX] 关键修复：允许 tool_result 或 toolResult
    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    @classmethod
    def validate_tool_result(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 兼容 toolResult (前端) 和 tool_result (后端/DB)
            tool_result_value = data.get('toolResult') or data.get('tool_result')
            if tool_result_value is None:
                data['toolResult'] = CallToolResult.failure("Missing tool result data")
        return data

# --- 其他内容定义 (同样加上 ConfigDict) ---
class FrontendToolRequest(BaseModel):
    type:str = "frontendToolRequest"
    id: str
    tool_call: ToolCall = Field(alias="toolCall")
    
    # [FIX]
    model_config = ConfigDict(populate_by_name=True)

class ToolConfirmationRequest(BaseModel):
    type: str = "toolConfirmationRequest"
    id: str
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")

    # [FIX]
    model_config = ConfigDict(populate_by_name=True)

class ActionRequiredData(BaseModel):
    type: str 
    tool_name: Optional[str] = Field(None, alias="toolName")
    tool_call_id: Optional[str] = Field(None, alias="toolCallId")
    message: Optional[str] = None
    id: Optional[str] = None

    # [FIX]
    model_config = ConfigDict(populate_by_name=True)

class ActionRequired(BaseModel):
    type: str = "actionRequired"
    data: ActionRequiredData

class ThinkingContent(BaseModel):
    type:str= "thinking"
    thinking: str
    signature: Optional[str] = None

class RedactedThinkingContent(BaseModel):
    type: str = "redactedThinking"

class SystemNotificationType(str, Enum):
    THINKING = "thinkingMessage"
    INLINE = "inlineMessage"

class SystemNotification(BaseModel):
    type: str = "systemNotification"
    notification_type: SystemNotificationType = Field(alias="notificationType")
    msg: str

    # [FIX]
    model_config = ConfigDict(populate_by_name=True)

# --- 消息聚合 ---
MessageContent = Union[
    TextContent, ImageContent, ToolRequest, ToolResponse,
    FrontendToolRequest, ToolConfirmationRequest, ActionRequired,
    ThinkingContent, RedactedThinkingContent, SystemNotification
]

class MessageMetadata(BaseModel):
    user_visible: bool = Field(default=True, alias="userVisible")
    agent_visible: bool = Field(default=True, alias="agentVisible")
    # 之前已经有这个了，保持不动
    model_config = ConfigDict(populate_by_name=True) 

    @classmethod
    def invisible(cls) -> "MessageMetadata":
        return cls(userVisible=False, agentVisible=False)

class Message(BaseModel):
    """
    支持智能构造的 Message 类
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="消息ID")
    role: Role = Field(default=Role.USER, description="消息角色")

    content: List[MessageContent] = Field(default_factory=list)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)

    session_id: Optional[str] = Field(default=None, description="所属会话ID")
    created_at: float = Field(default_factory=time.time, description="消息创建时间")
    
    # 之前已经有这个了，保持不动
    model_config = ConfigDict(populate_by_name=True)

    # ... (其余方法保持不变) ...
    @model_validator(mode='before')
    @classmethod
    def _normalize_before_validation(cls, data: Any) -> Any:
        # ... (保持原来的逻辑) ...
        if isinstance(data, dict):
            raw_content = data.get("content")
            if raw_content is None:
                data["content"] = []
                return data
            if isinstance(raw_content, str):
                data["content"] = [TextContent(text=raw_content)]
                return data
            if isinstance(raw_content, list):
                new_content = []
                for item in raw_content:
                    new_content.append(cls._parse_single_item(item))
                data["content"] = new_content
                return data
        
        if isinstance(data, cls):
            return data
        return data

    @classmethod
    def create(cls, role: Union[Role, str], content: Any, **kwargs) -> "Message":
        # ... (保持原来的逻辑) ...
        if isinstance(role, str):
            try:
                role = Role(role)
            except ValueError:
                role = Role.USER 

        normalized_content = cls._parse_content(content)
        return cls(role=role, content=normalized_content, **kwargs)

    @staticmethod
    def _parse_content(raw: Any) -> List[MessageContent]:
        # ... (保持原来的逻辑) ...
        if raw is None: return []
        if isinstance(raw, list): return [Message._parse_single_item(item) for item in raw]
        return [Message._parse_single_item(raw)]

    @staticmethod
    def _parse_single_item(item: Any) -> MessageContent:
        # ... (保持原来的逻辑) ...
        
        # 1. 已是对象
        if isinstance(item, (TextContent, ImageContent, ToolRequest, ToolResponse, FrontendToolRequest, ToolConfirmationRequest, ActionRequired, ThinkingContent, RedactedThinkingContent, SystemNotification)):
            return item
        # 2. 字符串
        if isinstance(item, str):
            return TextContent(text=item)
        # 3. 字典
        if isinstance(item, dict):
            known_types = ["text", "image", "toolRequest", "toolResponse", "frontendToolRequest", "toolConfirmationRequest", "actionRequired", "thinking", "redactedThinking", "systemNotification"]
            if item.get("type") in known_types:
                # 优化：如果是简单的 text 类型，直接转对象
                if item.get("type") == "text" and "text" in item:
                     return TextContent(text=str(item["text"]))
                
                # 重要：对于 ToolRequest 等复杂类型，返回 dict 让 Pydantic 校验。
                # 由于我们在 Class 定义中加了 populate_by_name=True，
                # 这里的 dict 即使包含 snake_case 键 (如 tool_call) 也能被正确转换。
                return item 

            # 其他情况转 TextContent
            extracted_text = item.get("content") or item.get("text") or item.get("result") or item.get("answer")
            if extracted_text is not None:
                if isinstance(extracted_text, (str, int, float, bool)):
                    return TextContent(text=str(extracted_text))
                return TextContent(text=json.dumps(extracted_text, ensure_ascii=False))
            
            try:
                return TextContent(text=json.dumps(item, ensure_ascii=False))
            except:
                return TextContent(text=str(item))

        if hasattr(item, "model_dump_json"):
            return TextContent(text=item.model_dump_json())

        return TextContent(text=str(item))

    # ... (Auxiliary properties and shortcuts remain the same) ...
    @property
    def tool_calls(self) -> List["ToolRequest"]:
        return [c for c in self.content if isinstance(c, ToolRequest)]

    @property
    def text(self) -> str:
        parts = []
        for c in self.content:
            if isinstance(c, TextContent):
                parts.append(c.text)
            elif isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
        return "\n".join(parts)

    def as_concat_text(self) -> str:
        return self.text

    @classmethod
    def system(cls, text: str = "") -> "Message":
        return cls.create(Role.SYSTEM, text)

    @classmethod
    def user(cls, text: str = "") -> "Message":
        return cls.create(Role.USER, text)

    @classmethod
    def assistant(cls, text: str = "") -> "Message":
        return cls.create(Role.ASSISTANT, text)
    
    @classmethod
    def tool(cls, text: str = "", tool_call_id: str = "") -> "Message":
        msg = cls(role=Role.TOOL)
        if text:
            msg.content.append(ToolResponse(
                id=tool_call_id, 
                toolResult=CallToolResult(content=[RawContent(text=text)])
            ))
        return msg