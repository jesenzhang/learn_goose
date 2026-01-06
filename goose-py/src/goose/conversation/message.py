import time
import json
from enum import Enum
from typing import List, Optional, Any, Dict, Union, Literal
from pydantic import BaseModel, Field, ConfigDict,model_validator
import uuid

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
    """
    支持智能构造的 Message 类
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="消息ID")
    role: Role = Field(default=Role.USER, description="消息角色")

    content: List[MessageContent] = Field(default_factory=list)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)

    session_id: Optional[str] = Field(default=None, description="所属会话ID")
    created_at: float = Field(default_factory=time.time, description="消息创建时间")
    
    model_config = ConfigDict(populate_by_name=True)

    # =========================================================================
    # 🛡️ 核心修复：前置拦截校验器 (Pre-validator)
    # =========================================================================
    @model_validator(mode='before')
    @classmethod
    def _normalize_before_validation(cls, data: Any) -> Any:
        """
        在 Pydantic 开始严格校验之前，拦截所有输入数据，
        将 字符串、字典 等非标准格式自动转换为 TextContent 对象。
        """
        # 1. 如果输入是 dict (标准用法)
        if isinstance(data, dict):
            raw_content = data.get("content")
            
            # 如果 content 缺失，设为空列表
            if raw_content is None:
                data["content"] = []
                return data

            # 如果 content 是字符串 -> 转为 [TextContent]
            if isinstance(raw_content, str):
                data["content"] = [TextContent(text=raw_content)]
                return data

            # 如果 content 是列表 -> 遍历清洗每一项
            if isinstance(raw_content, list):
                new_content = []
                for item in raw_content:
                    new_content.append(cls._parse_single_item(item))
                data["content"] = new_content
                return data

        # 2. 如果输入是 Message 对象本身 (防守性编程)
        if isinstance(data, cls):
            return data

        return data
    
    # -------------------------------------------------------------------------
    # 🏭 工厂方法 (新增)
    # -------------------------------------------------------------------------
    
    @classmethod
    def create(cls, role: Union[Role, str], content: Any, **kwargs) -> "Message":
        """
        [智能构造器] 接收任意格式的 content，自动清洗并封装。
        示例:
            Message.create("user", "Hello")
            Message.create("assistant", {"text": "Hi"})
            Message.create("tool", some_tool_response_obj)
        """
        # 1. 归一化 Role
        if isinstance(role, str):
            try:
                role = Role(role)
            except ValueError:
                role = Role.USER # 兜底，或者抛错

        # 2. 归一化 Content
        normalized_content = cls._parse_content(content)

        return cls(role=role, content=normalized_content, **kwargs)

    # -------------------------------------------------------------------------
    # 🛠️ 内部解析逻辑 (新增)
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_content(raw: Any) -> List[MessageContent]:
        """将杂乱的输入转换为标准的 List[MessageContent]"""
        if raw is None:
            return []

        # 如果已经是列表，递归处理每一项
        if isinstance(raw, list):
            return [Message._parse_single_item(item) for item in raw]

        # 如果是单个对象
        return [Message._parse_single_item(raw)]

    @staticmethod
    def _parse_single_item(item: Any) -> MessageContent:
        """核心逻辑：识别并转换单个内容块"""
        
        # 1. 已经是合法的 Pydantic 模型 (TextContent, ToolRequest 等)
        # 这里的类型检查依赖于 item 是否是 MessageContent 中定义的类型的实例
        if isinstance(item, (
            TextContent, ImageContent, ToolRequest, ToolResponse,
            FrontendToolRequest, ToolConfirmationRequest, ActionRequired,
            ThinkingContent, RedactedThinkingContent, SystemNotification
        )):
            return item

        # 2. 字符串 -> TextContent
        if isinstance(item, str):
            return TextContent(text=item)

        # 3. 字典 -> 智能识别
        if isinstance(item, dict):
            # A. 如果字典显式指定了 'type'，且匹配我们支持的类型，尝试让 Pydantic 自动转换
            # (这通常发生在反序列化 DB 数据时)
            known_types = [
                "text", "image", "toolRequest", "toolResponse", 
                "frontendToolRequest", "toolConfirmationRequest", 
                "actionRequired", "thinking", "redactedThinking", "systemNotification"
            ]
            if item.get("type") in known_types:
                # 返回原始字典，Pydantic 的 Union 校验器会自动根据 Discriminator (type) 实例化正确的类
                # 注意：这要求调用方最终将此列表传给 Message 构造函数
                # 但为了安全起见，我们在这里也可以手动实例化 TextContent，
                # 对于复杂对象，我们假设 Pydantic 稍后会处理它，或者我们在此处直接返回 dict
                # 在 List[Union[...]] 中，Pydantic 可以处理 dict，只要结构匹配。
                
                # 特殊优化：如果是简单的 text 类型，直接转对象，避免后续校验开销
                if item.get("type") == "text" and "text" in item:
                     return TextContent(text=str(item["text"]))
                
                # 其他复杂类型 (如 ToolResponse)，返回 dict 也是可以的，
                # 但为了类型安全，最好这里不做处理，让它落入 Pydantic 的验证流程。
                # 但 create 方法返回的是 Message 实例，其实例化时会执行验证。
                # 为了简化，我们把 dict 视为“潜在的合法对象”，直接尝试转换成 TextContent 兜底
                # 只有当它完全符合复杂对象结构时才保留。
                return item # type: ignore (Pydantic will validate this)

            # B. 字典是 LLM 的原始输出 (包含 content/result/text 字段)
            # 这种通常没有 'type' 字段，或者 'type' 不在我们系统定义的范围内
            extracted_text = (
                item.get("content") or 
                item.get("text") or 
                item.get("result") or 
                item.get("answer")
            )
            if extracted_text is not None:
                # 递归处理提取出来的内容
                if isinstance(extracted_text, (str, int, float, bool)):
                    return TextContent(text=str(extracted_text))
                # 如果提取出来还是个字典/列表，递归解析
                # 这里简化处理：直接转 JSON
                return TextContent(text=json.dumps(extracted_text, ensure_ascii=False))

            # C. 无法识别的字典 -> 转 JSON 字符串
            try:
                return TextContent(text=json.dumps(item, ensure_ascii=False))
            except:
                return TextContent(text=str(item))

        # 4. 其他 Pydantic 对象 (非 MessageContent 成员) -> 序列化为字符串
        if hasattr(item, "model_dump_json"):
            return TextContent(text=item.model_dump_json())

        # 5. 兜底 -> 强转字符串
        return TextContent(text=str(item))

    # -------------------------------------------------------------------------
    # 📖 辅助属性 (保持不变，用于兼容性)
    # -------------------------------------------------------------------------

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
    
    
    # -------------------------------------------------------------------------
    # 🏗️ 快捷构造器 (保持不变)
    # -------------------------------------------------------------------------

    @classmethod
    def system(cls, text: str = "") -> "Message":
        return cls.create(Role.SYSTEM, text)

    @classmethod
    def user(cls, text: str = "") -> "Message":
        return cls.create(Role.USER, text)

    @classmethod
    def assistant(cls, text: str = "") -> "Message":
        return cls.create(Role.ASSISTANT, text)
    
    # Tool 比较特殊，通常不用 create 传字符串，而是传结构体，但这里兼容一下
    @classmethod
    def tool(cls, text: str = "", tool_call_id: str = "") -> "Message":
        msg = cls(role=Role.TOOL)
        if text:
            # 使用现有的复杂结构
            msg.content.append(ToolResponse(
                id=tool_call_id, 
                toolResult=CallToolResult(content=[RawContent(text=text)])
            ))
        return msg