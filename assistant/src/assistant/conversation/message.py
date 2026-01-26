import time
import json
from enum import Enum
from typing import List, Optional, Any, Dict, Union, Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator, BeforeValidator

import uuid

# --- 基础内容定义 ---
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class TextContent(BaseModel):
    type: Literal["text"] = "text" # [关键修改] 使用 Literal
    text: str
    model_config = ConfigDict(populate_by_name=True)

class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    data: str
    mime_type: str = Field(alias="mimeType")
    model_config = ConfigDict(populate_by_name=True)

class RawContent(BaseModel):
    """工具返回的原始内容 (通常嵌套在 ToolResponse 中)"""
    type: str = "text" # RawContent 比较灵活，可以保持 str，或者也做成 Literal
    text: Optional[str] = None
    data: Optional[Any] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")
    
    # Artifact 增强信息
    title: Optional[str] = None       
    id: Optional[str] = None          
    metadata: Optional[Dict[str, Any]] = None 
    
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
    type: Literal["tool_request","toolRequest"] = "tool_request" # [关键修改]
    id: str
    tool_call: ToolCall = Field(alias="toolCall")
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    @classmethod
    def validate_tool_call(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 兼容 toolCall (前端) 和 tool_call (后端/DB)
            tool_call_value = data.get('toolCall') or data.get('tool_call')
            
            # 如果 tool_call_value 已经是 dict，无需处理，Pydantic 会自动转换
            # 如果缺失，则填充错误
            if tool_call_value is None:
                data['toolCall'] = ToolCall.failure("Missing tool call data").model_dump()
            elif tool_call_value:
                # 确保赋值给 alias 对应的 key，以便 Pydantic 识别
                data['toolCall'] = tool_call_value
        return data

# --- 工具结果 (Result) 相关 ---
class CallToolResult(BaseModel):
    """用于 Result：封装工具执行输出"""
    content: List[RawContent] = Field(default_factory=list)
    is_error: bool = Field(default=False, alias="isError")
    metadata: Optional[Dict[str, Any]] = None

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
    type: Literal["tool_response","toolResponse"] = "tool_response" # [关键修改]
    id: str
    tool_result: CallToolResult = Field(alias="toolResult")
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    @classmethod
    def validate_tool_result(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 兼容 toolResult (前端) 和 tool_result (后端/DB)
            tool_result_value = data.get('toolResult') or data.get('tool_result')
            
            if tool_result_value is None:
                data['toolResult'] = CallToolResult.failure("Missing tool result data").model_dump()
            else:
                data['toolResult'] = tool_result_value
        return data

# --- 其他内容定义 ---
class FrontendToolRequest(BaseModel):
    type: Literal["frontend_tool_request","frontendToolRequest"] = "frontend_tool_request"
    id: str
    tool_call: ToolCall = Field(alias="toolCall")
    model_config = ConfigDict(populate_by_name=True)

class ToolConfirmationRequest(BaseModel):
    type: Literal["tool_confirmation_request","toolConfirmationRequest"] = "tool_confirmation_request"
    id: str
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    model_config = ConfigDict(populate_by_name=True)

class ActionRequiredData(BaseModel):
    type: str 
    tool_name: Optional[str] = Field(None, alias="toolName")
    tool_call_id: Optional[str] = Field(None, alias="toolCallId")
    message: Optional[str] = None
    id: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True)

class ActionRequired(BaseModel):
    type: Literal["action_required","actionRequired"] = "action_required"
    data: ActionRequiredData
    model_config = ConfigDict(populate_by_name=True)

class ThinkingContent(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True)

class RedactedThinkingContent(BaseModel):
    type: Literal["redacted_thinking","redactedThinking"] = "redacted_thinking"
    model_config = ConfigDict(populate_by_name=True)

class SystemNotificationType(str, Enum):
    THINKING = "thinkingMessage"
    INLINE = "inlineMessage"

class SystemNotification(BaseModel):
    type: Literal["system_notification","systemNotification"] = "system_notification"
    notification_type: SystemNotificationType = Field(alias="notificationType")
    msg: str
    model_config = ConfigDict(populate_by_name=True)

# --- [关键修改] 消息聚合与鉴别器 ---
# 使用 Annotated 和 discriminator 让 Pydantic 自动根据 type 字段决定实例化哪个类
MessageContent = Annotated[
    Union[
        TextContent, 
        ImageContent, 
        ToolRequest, 
        ToolResponse,
        FrontendToolRequest, 
        ToolConfirmationRequest, 
        ActionRequired,
        ThinkingContent, 
        RedactedThinkingContent, 
        SystemNotification
    ],
    Field(discriminator="type") 
]

class MessageVisible(BaseModel):
    user_visible: bool = Field(default=True, alias="userVisible")
    agent_visible: bool = Field(default=True, alias="agentVisible")
    model_config = ConfigDict(populate_by_name=True) 

    @classmethod
    def invisible(cls) -> "MessageVisible":
        return cls(userVisible=False, agentVisible=False)

class Message(BaseModel):
    """
    支持智能构造的 Message 类
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="消息ID")
    role: str = Field(default=Role.USER, description="消息角色")

    # Pydantic 会根据 discriminator 自动解析这里的列表
    content: List[MessageContent] = Field(default_factory=list)
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="消息元数据")
    visible: MessageVisible  = Field(default_factory=MessageVisible, description="消息可见性设置")
    session_id: Optional[int] = Field(default=None, description="所属会话ID")
    created_at: float = Field(default_factory=time.time, description="消息创建时间")
    
    model_config = ConfigDict(populate_by_name=True)

    def with_visibility(self, user_visible: bool = True, agent_visible: bool = True) -> "Message":
        self.visible.user_visible = user_visible
        self.visible.agent_visible = agent_visible
        return self
    
    def only_user_visible(self) -> "Message":
        return self.with_visibility(user_visible=True, agent_visible=False)
    
    def only_agent_visible(self) -> "Message":
        return self.with_visibility(user_visible=False, agent_visible=True)
    
    # --- 核心序列化与反序列化逻辑 ---
    @property
    def content_json(self) -> str:
        """将 content 序列化为 JSON 字符串"""
        content_data = [
            c.model_dump(mode='json', by_alias=True, exclude_none=True) 
            for c in self.content
        ]
        content_json = json.dumps(content_data, ensure_ascii=False)
        return content_json
    
    @property
    def meta_json(self) -> str:
        """将 content 序列化为 JSON 字符串"""
        meta = {}
        meta.update(self.metadata)
        meta.update({
            "created_at":self.created_at,
            "visible":self.visible.model_dump(),
            "id":self.id,
            "session_id":self.session_id
        })
        
        meta_json = json.dumps(meta, ensure_ascii=False)
        return meta_json
    
    @model_validator(mode='before')
    @classmethod
    def _normalize_before_validation(cls, data: Any) -> Any:
        """
        在 Pydantic 严格验证之前，进行数据清洗和标准化。
        处理 DB 字符串、简写格式等。
        """
        if isinstance(data, dict):
            # 1. 处理 metadata (DB 可能存为 JSON 字符串)
            metadata = {}
            raw_metadata = data.get("metadata")
            if raw_metadata:
                if isinstance(raw_metadata, str):
                    try:
                        metadata = json.loads(raw_metadata)
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                elif isinstance(raw_metadata, dict):
                    metadata = raw_metadata
                    
            # 2. 处理 metadata (DB 可能存为 JSON 字符串)
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            if "session_id" not in data and "session_id" in metadata:
                data["session_id"] = metadata.pop("session_id")
            
            if "created_at" not in data and "created_at" in metadata:
                data["created_at"] = metadata.pop("created_at")
            else:
                data["created_at"] = 0.0
                
            if "id" not in data and "id" in metadata:
                data["id"] = metadata.pop("id")
            
            if "visible" not in data and "visible" in metadata:
                data["visible"] = metadata.pop("visible")
            
             # 2. 处理 visible (DB 可能存为 JSON 字符串)
            raw_visible = data.get("visible")
            if isinstance(raw_visible, str):
                try:
                    data["visible"] = json.loads(raw_visible)
                except:
                    pass
            
            data['metadata'] = metadata
            # 3. 处理 content 字段
            # 目标：将所有奇怪的输入都转化为 List[Dict]，且每个 Dict 都有 'type' 字段
            # 这样后续 Pydantic 的 discriminator 才能正常工作
            raw_content = data.get("content")
            
            if raw_content is None:
                data["content"] = []
                return data
            
            # Case A: 数据库返回的是 JSON 字符串 (这是我们刚才存进去的格式)
            if isinstance(raw_content, str):
                try:
                    # 尝试解析 JSON
                    parsed_content = json.loads(raw_content)
                    
                    # 如果解析出来是列表，说明是结构化数据 -> 替换 raw_content 继续往下走
                    if isinstance(parsed_content, list):
                        raw_content = parsed_content
                    else:
                        # 如果解析出来不是列表（或者是普通字符串），就当作纯文本 TextContent
                        data["content"] = [{"type": "text", "text": raw_content}]
                        return data
                except (json.JSONDecodeError, TypeError):
                    # 解析失败，说明它真的一条普通文本消息
                    data["content"] = [{"type": "text", "text": raw_content}]
                    return data
            
            # Case B: 列表 -> 规范化列表中的每一项
            if isinstance(raw_content, list):
                new_content = []
                for item in raw_content:
                    normalized_item = cls._normalize_single_content_item(item)
                    if normalized_item:
                        new_content.append(normalized_item)
                data["content"] = new_content
                return data

        return data

    @staticmethod
    def _normalize_single_content_item(item: Any) -> Optional[Dict[str, Any]]:
        """将单个内容项转化为符合 Pydantic 鉴别器要求的 Dict"""
        # 1. 已经是 Pydantic 对象 -> 转 Dict
        if isinstance(item, BaseModel):
            return item.model_dump(by_alias=True)
        
        # 2. 字符串 -> TextContent Dict
        if isinstance(item, str):
            return {"type": "text", "text": item}
        
        # 3. 字典 -> 检查并补全
        if isinstance(item, dict):
            # 如果没有 type，尝试推断 (简单处理，通常应有 type)
            if "type" not in item:
                if "text" in item:
                    item["type"] = "text"
                elif "toolCall" in item or "tool_call" in item:
                    item["type"] = "tool_request"
                elif "toolResult" in item or "tool_result" in item:
                    item["type"] = "tool_response"
                elif "thinking" in item:
                    item["type"] = "thinking"
                else:
                    # 兜底：转为文本
                    return {"type": "text", "text": str(item)}
            
            # 针对 TextContent 的特殊处理：如果 type=text 但 data 是复杂对象
            if item["type"] == "text" and not isinstance(item.get("text"), str):
                 item["text"] = str(item.get("text", ""))
                 
            return item
            
        return {"type": "text", "text": str(item)}

    # --- 快捷构造方法 ---

    @classmethod
    def create(cls, role: Union[Role, str], content: Any, **kwargs) -> "Message":
        """便捷工厂方法"""
        if isinstance(role, str):
            try:
                role = Role(role)
            except ValueError:
                role = Role.USER 
        
        # 利用 model_validate 的自动清洗能力
        # 我们构造一个初步的 dict，让 Pydantic 走 _normalize_before_validation
        temp_data = {
            "role": role,
            "content": content,
            **kwargs
        }
        return cls.model_validate(temp_data)

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
    def tool_response(cls, tool_response: ToolResponse, metadata: Dict[str, Any] = None) -> "Message":
        return cls(role=Role.TOOL, content=[tool_response], metadata=metadata).only_agent_visible()
    
    @classmethod
    def tool_responses(cls, tool_responses: List[ToolResponse], metadata: Dict[str, Any] = None) -> "Message":
        return cls(role=Role.TOOL, content=tool_responses, metadata=metadata).only_agent_visible()
    
    @classmethod
    def tool_request(cls, tool_request: ToolRequest, metadata: Dict[str, Any] = None) -> "Message":
        return cls(role=Role.ASSISTANT, content=[tool_request], metadata=metadata).only_agent_visible()

    @classmethod
    def tool_requests(cls, tool_requests: List[ToolRequest], metadata: Dict[str, Any] = None) -> "Message":
        return cls(role=Role.ASSISTANT, content=tool_requests, metadata=metadata).only_agent_visible()
    
    @classmethod
    def tool(cls, text: str = "", data: dict = None, tool_call_id: str = "", metadata: Any = None) -> "Message":
        """快速创建一个工具响应消息"""
        # 构造 ToolResponse 对象
        tr = ToolResponse(
            id=tool_call_id,
            toolResult=CallToolResult(content=[RawContent(text=text, data=data)])
        )
        return cls(role=Role.TOOL, content=[tr], metadata=metadata).only_agent_visible()

    # --- 辅助属性 ---
    @property
    def visible_to_user(self) -> bool:
        return self.visible.user_visible

    @property
    def visible_to_agent(self) -> bool:
        return self.visible.agent_visible
    
    @property
    def text(self) -> str:
        """获取所有文本内容的拼接"""
        parts = []
        for c in self.content:
            if isinstance(c, TextContent):
                parts.append(c.text)
            # 也可以选择性地包含其他类型的文本表示
        return "\n".join(parts)
    
    @property
    def tool_calls(self) -> List[ToolRequest]:
        return [c for c in self.content if isinstance(c, ToolRequest)]