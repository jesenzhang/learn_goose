"""
Conversation

对话管理模块，参考 goose-rs 实现。
使用 Pydantic DiscriminatedUnion 实现多种消息内容类型的序列。

参考: goose-rs/crates/goose/src/conversation/message.rs
"""

from typing import List, Dict, Any, Optional, Union
from enum import Enum
from datetime import datetime
import uuid
import json

from pydantic import BaseModel, Field, ConfigDict, model_validator


class Role(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class SystemNotificationType(str, Enum):
    """系统通知类型"""
    THINKING_MESSAGE = "thinkingMessage"
    INLINE_MESSAGE = "inlineMessage"


class ActionType(str, Enum):
    """操作类型"""
    TOOL_CONFIRMATION = "toolConfirmation"
    ELICITATION = "elicitation"
    ELICITATION_RESPONSE = "elicitationResponse"


# =============================================================================
# Content Types (Pydantic Models)
# =============================================================================

class TextContent(BaseModel):
    """文本内容"""
    text: str
    type: str = "text"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(cls, text: str) -> "TextContent":
        return cls(text=text)
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}


class ImageContent(BaseModel):
    """图像内容（支持 URL 和 base64）"""
    data: str
    url: Optional[str] = None
    mime_type: str = "image/png"
    detail: str = "auto"
    type: str = "image"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(
        cls,
        data: str,
        mime_type: str = "image/png",
        url: Optional[str] = None,
        detail: str = "auto"
    ) -> "ImageContent":
        if url:
            return cls(data="", url=url, mime_type=mime_type, detail=detail)
        return cls(data=data, mime_type=mime_type, detail=detail)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": "image",
            "mimeType": self.mime_type,
            "detail": self.detail
        }
        if self.url:
            result["source"] = {"type": "url", "url": self.url}
        elif self.data:
            result["source"] = {
                "type": "base64",
                "mediaType": self.mime_type,
                "data": self.data
            }
        return result

    def to_openai_dict(self) -> Dict[str, Any]:
        """
        转换为 OpenAI API 格式

        OpenAI 期望: {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}
        """
        if self.url:
            return {
                "type": "image_url",
                "image_url": {
                    "url": self.url,
                    "detail": self.detail
                }
            }
        elif self.data:
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{self.mime_type};base64,{self.data}",
                    "detail": self.detail
                }
            }
        return {
            "type": "image_url",
            "image_url": {"detail": self.detail}
        }

    def to_anthropic_dict(self) -> Dict[str, Any]:
        """
        转换为 Anthropic API 格式

        Anthropic 期望: {"type": "image", "source": {"type": "url", "url": "..."}}
        或 {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}
        """
        if self.url:
            return {
                "type": "image",
            "source": {
                "type": "url",
                "url": self.url
            }
            }
        elif self.data:
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.mime_type,
                    "data": self.data
                }
            }
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": self.mime_type, "data": ""}
        }


class AudioContent(BaseModel):
    """音频内容"""
    data: str
    url: Optional[str] = None
    format: str = "wav"
    mime_type: str = "audio/wav"
    type: str = "audio"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(
        cls,
        data: str,
        format: str = "wav",
        url: Optional[str] = None
    ) -> "AudioContent":
        if url:
            return cls(data="", url=url, format=format, mime_type=f"audio/{format}")
        return cls(data=data, format=format, mime_type=f"audio/{format}")
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": "audio",
            "format": self.format,
            "mimeType": self.mime_type
        }
        if self.url:
            result["source"] = {"type": "url", "url": self.url}
        elif self.data:
            result["source"] = {
                "type": "base64",
                "mediaType": self.mime_type,
                "data": self.data
            }
        return result


class ToolRequestContentValue(BaseModel):
    """工具请求内容值"""
    name: str
    arguments: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(populate_by_name=True)
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"name": self.name}
        if self.arguments is not None:
            result["arguments"] = self.arguments
        return result


class ToolRequestContent(BaseModel):
    """工具请求内容"""
    id: str
    tool_call: Dict[str, Any] = Field(default_factory=dict, alias="toolCall")
    type: str = "tool_request"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @property
    def tool_call_value(self) -> Optional[ToolRequestContentValue]:
        """获取 tool_call 中的 value"""
        if self.tool_call.get("status") == "success":
            value = self.tool_call.get("value")
            if value:
                return ToolRequestContentValue(**value)
        return None
    
    @classmethod
    def create(
        cls,
        tool_id: str,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> "ToolRequestContent":
        return cls(
            id=tool_id,
            tool_call={
                "status": "success",
                "value": {"name": name, "arguments": arguments}
            }
        )
    
    @classmethod
    def create_error(cls, tool_id: str, error: str) -> "ToolRequestContent":
        return cls(
            id=tool_id,
            tool_call={
                "status": "error",
                "error": error
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_request",
            "id": self.id,
            "toolCall": self.tool_call
        }


class ToolResponseContent(BaseModel):
    """工具响应内容"""
    id: str
    tool_result: Dict[str, Any] = Field(default_factory=dict, alias="toolResult")
    type: str = "tool_response"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @property
    def content(self) -> List[Dict[str, Any]]:
        return self.tool_result.get("content", [])
    
    @property
    def is_error(self) -> bool:
        return self.tool_result.get("isError", False)
    
    @classmethod
    def create(
        cls,
        tool_id: str,
        content: List[Dict[str, Any]],
        is_error: bool = False
    ) -> "ToolResponseContent":
        return cls(
            id=tool_id,
            tool_result={
                "content": content,
                "isError": is_error
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_response",
            "id": self.id,
            "toolResult": self.tool_result
        }


class ToolConfirmationRequestContent(BaseModel):
    """工具确认请求内容"""
    id: str
    tool_confirmation_request: Dict[str, Any] = Field(default_factory=dict, alias="toolConfirmationRequest")
    type: str = "tool_confirmation_request"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(
        cls,
        tool_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> "ToolConfirmationRequestContent":
        req: Dict[str, Any] = {
            "toolName": tool_name,
            "arguments": arguments
        }
        if prompt:
            req["prompt"] = prompt
        return cls(
            id=tool_id,
            tool_confirmation_request=req
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_confirmation_request",
            "id": self.id,
            "toolConfirmationRequest": self.tool_confirmation_request
        }


class ActionRequiredElicitation(BaseModel):
    """征询内容"""
    message: str
    requested_schema: Dict[str, Any] = Field(alias="requestedSchema")
    
    model_config = ConfigDict(populate_by_name=True)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "requestedSchema": self.requested_schema
        }


class ActionRequiredElicitationResponse(BaseModel):
    """征询响应内容"""
    user_data: Dict[str, Any] = Field(alias="userData")
    
    model_config = ConfigDict(populate_by_name=True)
    
    def to_dict(self) -> Dict[str, Any]:
        return {"userData": self.user_data}


class ActionRequiredContent(BaseModel):
    """操作必需内容"""
    id: str
    action_type: str = Field(alias="actionType")
    tool_name: Optional[str] = Field(default=None, alias="toolName")
    arguments: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    elicitation: Optional[ActionRequiredElicitation] = None
    elicitation_response: Optional[ActionRequiredElicitationResponse] = None
    type: str = "action_required"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create_tool_confirmation(
        cls,
        action_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> "ActionRequiredContent":
        return cls(
            id=action_id,
            action_type=ActionType.TOOL_CONFIRMATION,
            tool_name=tool_name,
            arguments=arguments,
            prompt=prompt
        )
    
    @classmethod
    def create_elicitation(
        cls,
        action_id: str,
        message: str,
        requested_schema: Dict[str, Any]
    ) -> "ActionRequiredContent":
        return cls(
            id=action_id,
            action_type=ActionType.ELICITATION,
            elicitation=ActionRequiredElicitation(
                message=message,
                requested_schema=requested_schema
            )
        )
    
    @classmethod
    def create_elicitation_response(
        cls,
        action_id: str,
        user_data: Dict[str, Any]
    ) -> "ActionRequiredContent":
        return cls(
            id=action_id,
            action_type=ActionType.ELICITATION_RESPONSE,
            elicitation_response=ActionRequiredElicitationResponse(user_data=user_data)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "type": "action_required",
            "actionType": self.action_type,
            "id": self.id
        }
        
        if self.action_type == ActionType.TOOL_CONFIRMATION:
            result["toolName"] = self.tool_name
            result["arguments"] = self.arguments or {}
            if self.prompt:
                result["prompt"] = self.prompt
        elif self.action_type == ActionType.ELICITATION and self.elicitation:
            result["message"] = self.elicitation.message
            result["requestedSchema"] = self.elicitation.requested_schema
        elif self.action_type == ActionType.ELICITATION_RESPONSE and self.elicitation_response:
            result["userData"] = self.elicitation_response.user_data
        
        return result


class ThinkingContent(BaseModel):
    """思考内容"""
    thinking: str
    signature: str = ""
    type: str = "thinking"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(cls, thinking: str, signature: str = "") -> "ThinkingContent":
        return cls(thinking=thinking, signature=signature)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "thinking",
            "thinking": self.thinking,
            "signature": self.signature
        }


class RedactedThinkingContent(BaseModel):
    """已编辑思考内容"""
    data: str
    type: str = "redacted_thinking"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(cls, data: str) -> "RedactedThinkingContent":
        return cls(data=data)
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": "redacted_thinking", "data": self.data}


class FrontendToolRequestContent(BaseModel):
    """前端工具请求内容"""
    id: str
    frontend_tool_request: Dict[str, Any] = Field(default_factory=dict, alias="frontendToolRequest")
    type: str = "frontend_tool_request"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(
        cls,
        request_id: str,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> "FrontendToolRequestContent":
        return cls(
            id=request_id,
            frontend_tool_request={"name": name, "arguments": arguments or {}}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "frontend_tool_request",
            "id": self.id,
            "frontendToolRequest": self.frontend_tool_request
        }


class SystemNotificationContent(BaseModel):
    """系统通知内容"""
    notification_type: SystemNotificationType = Field(alias="notificationType")
    msg: str
    type: str = "system_notification"
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def create(
        cls,
        notification_type: SystemNotificationType,
        msg: str
    ) -> "SystemNotificationContent":
        return cls(notification_type=notification_type, msg=msg)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "system_notification",
            "notificationType": self.notification_type.value,
            "msg": self.msg
        }


# =============================================================================
# Discriminated Union for MessageContent
# =============================================================================

MessageContent = Union[
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
]


def parse_message_content(data: Dict[str, Any]) -> MessageContent:
    """解析消息内容 (工厂函数)"""
    content_type = data.get("type", "text")
    
    # Handle both snake_case and camelCase for backward compatibility
    type_mapping = {
        "text": "text",
        "image": "image",
        "tool_request": "tool_request",
        "toolRequest": "tool_request",
        "tool_response": "tool_response",
        "toolResponse": "tool_response",
        "tool_confirmation_request": "tool_confirmation_request",
        "toolConfirmationRequest": "tool_confirmation_request",
        "action_required": "action_required",
        "actionRequired": "action_required",
        "thinking": "thinking",
        "redacted_thinking": "redacted_thinking",
        "redactedThinking": "redacted_thinking",
        "frontend_tool_request": "frontend_tool_request",
        "frontendToolRequest": "frontend_tool_request",
        "system_notification": "system_notification",
        "systemNotification": "system_notification",
    }
    
    normalized_type = type_mapping.get(content_type, content_type)
    
    if normalized_type == "text":
        return TextContent(**data)
    elif normalized_type == "image":
        return ImageContent(**data)
    elif normalized_type == "audio":
        return AudioContent(**data)
    elif normalized_type == "tool_request":
        return ToolRequestContent(**data)
    elif normalized_type == "tool_response":
        return ToolResponseContent(**data)
    elif normalized_type == "tool_confirmation_request":
        return ToolConfirmationRequestContent(**data)
    elif normalized_type == "action_required":
        return ActionRequiredContent(**data)
    elif normalized_type == "thinking":
        return ThinkingContent(**data)
    elif normalized_type == "redacted_thinking":
        return RedactedThinkingContent(**data)
    elif normalized_type == "frontend_tool_request":
        return FrontendToolRequestContent(**data)
    elif normalized_type == "system_notification":
        return SystemNotificationContent(**data)
    
    return TextContent(**data)


# =============================================================================
# Message Metadata
# =============================================================================

class MessageMetadata(BaseModel):
    """消息元数据"""
    user_visible: bool = Field(default=True, alias="userVisible")
    agent_visible: bool = Field(default=True, alias="agentVisible")
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def agent_only(cls) -> "MessageMetadata":
        return cls(user_visible=False, agent_visible=True)
    
    @classmethod
    def user_only(cls) -> "MessageMetadata":
        return cls(user_visible=True, agent_visible=False)
    
    @classmethod
    def invisible(cls) -> "MessageMetadata":
        return cls(user_visible=False, agent_visible=False)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "userVisible": self.user_visible,
            "agentVisible": self.agent_visible,
            "attachments": self.attachments
        }


# =============================================================================
# Message
# =============================================================================

class Message(BaseModel):
    """
    消息
    
    参考 goose-rs crates/goose/src/conversation/message.rs 实现
    """
    role: Role
    content: List[MessageContent] = Field(default_factory=list)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)
    
    model_config = ConfigDict(populate_by_name=True)
    
    @classmethod
    def system(cls, text: str) -> "Message":
        return cls(
            role=Role.SYSTEM,
            content=[TextContent(text=text)],
            metadata=MessageMetadata()
        )
    
    @classmethod
    def user(
        cls,
        text: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> "Message":
        content = [TextContent(text=text)]
        metadata = MessageMetadata(attachments=attachments or [])
        return cls(
            role=Role.USER,
            content=content,
            metadata=metadata
        )
    
    @classmethod
    def assistant(cls, text: str = "") -> "Message":
        content = [TextContent(text=text)] if text else []
        return cls(
            role=Role.ASSISTANT,
            content=content,
            metadata=MessageMetadata()
        )
    
    @classmethod
    def tool_result(
        cls,
        tool_call_id: str,
        result: Any,
        is_error: bool = False
    ) -> "Message":
        if isinstance(result, list):
            content_list = result
        elif isinstance(result, dict):
            content_list = [result]
        else:
            content_list = [{"type": "text", "text": str(result)}]
        
        return cls(
            role=Role.TOOL,
            content=[ToolResponseContent.create(tool_call_id, content_list, is_error)],
            metadata=MessageMetadata()
        )
    
    def with_text(self, text: str) -> "Message":
        self.content.append(TextContent(text=text))
        return self
    
    def with_image(
        self,
        data: str = "",
        url: Optional[str] = None,
        mime_type: str = "image/png",
        detail: str = "auto"
    ) -> "Message":
        self.content.append(ImageContent.create(data, mime_type, url, detail))
        return self
    
    def with_tool_request(
        self,
        tool_id: str,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> "Message":
        self.content.append(ToolRequestContent.create(tool_id, name, arguments))
        return self
    
    def with_tool_response(
        self,
        tool_id: str,
        content: List[Dict[str, Any]],
        is_error: bool = False
    ) -> "Message":
        self.content.append(ToolResponseContent.create(tool_id, content, is_error))
        return self
    
    def with_thinking(self, thinking: str, signature: str = "") -> "Message":
        self.content.append(ThinkingContent.create(thinking, signature))
        return self
    
    def with_redacted_thinking(self, data: str) -> "Message":
        self.content.append(RedactedThinkingContent.create(data))
        return self
    
    def with_action_required_tool_confirmation(
        self,
        action_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> "Message":
        self.content.append(ActionRequiredContent.create_tool_confirmation(
            action_id, tool_name, arguments, prompt
        ))
        return self
    
    def with_action_required_elicitation(
        self,
        action_id: str,
        message: str,
        requested_schema: Dict[str, Any]
    ) -> "Message":
        self.content.append(ActionRequiredContent.create_elicitation(
            action_id, message, requested_schema
        ))
        return self
    
    def with_action_required_elicitation_response(
        self,
        action_id: str,
        user_data: Dict[str, Any]
    ) -> "Message":
        self.content.append(ActionRequiredContent.create_elicitation_response(
            action_id, user_data
        ))
        return self
    
    def with_tool_confirmation_request(
        self,
        tool_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> "Message":
        self.content.append(ToolConfirmationRequestContent.create(
            tool_id, tool_name, arguments, prompt
        ))
        return self
    
    def with_frontend_tool_request(
        self,
        request_id: str,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> "Message":
        self.content.append(FrontendToolRequestContent.create(request_id, name, arguments))
        return self
    
    def with_system_notification(
        self,
        notification_type: SystemNotificationType,
        msg: str
    ) -> "Message":
        self.content.append(SystemNotificationContent.create(notification_type, msg))
        self.metadata = MessageMetadata.user_only()
        return self
    
    def with_visibility(self, user_visible: bool, agent_visible: bool) -> "Message":
        self.metadata = MessageMetadata(user_visible=user_visible, agent_visible=agent_visible)
        return self
    
    def with_metadata(self, metadata: MessageMetadata) -> "Message":
        self.metadata = metadata
        return self
    
    def user_only(self) -> "Message":
        self.metadata = MessageMetadata.user_only()
        return self
    
    def agent_only(self) -> "Message":
        self.metadata = MessageMetadata.agent_only()
        return self
    
    @property
    def is_user_visible(self) -> bool:
        return self.metadata.user_visible
    
    @property
    def is_agent_visible(self) -> bool:
        return self.metadata.agent_visible
    
    def as_concat_text(self) -> str:
        texts = []
        for c in self.content:
            if isinstance(c, TextContent):
                texts.append(c.text)
        return "\n".join(texts)
    
    def is_tool_call(self) -> bool:
        return any(isinstance(c, ToolRequestContent) for c in self.content)
    
    def is_tool_response(self) -> bool:
        return any(isinstance(c, ToolResponseContent) for c in self.content)
    
    def get_tool_request_ids(self) -> List[str]:
        ids = []
        for c in self.content:
            if isinstance(c, ToolRequestContent):
                ids.append(c.id)
        return ids
    
    def has_only_text_content(self) -> bool:
        return all(isinstance(c, TextContent) for c in self.content)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "created": self.created,
            "content": [c.to_dict() for c in self.content],
            "metadata": self.metadata.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        role = Role(data.get("role", "user"))
        content = [
            parse_message_content(c) 
            for c in data.get("content", [])
        ]
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            role=role,
            created=data.get("created", int(datetime.now().timestamp())),
            content=content,
            metadata=MessageMetadata(
                user_visible=data.get("metadata", {}).get("userVisible", True),
                agent_visible=data.get("metadata", {}).get("agentVisible", True)
            )
        )
    
    def __repr__(self) -> str:
        return f"Message(role={self.role.value}, content_count={len(self.content)})"


# =============================================================================
# Conversation
# =============================================================================

class Conversation:
    """对话历史"""
    
    def __init__(self, messages: Optional[List[Message]] = None):
        self.messages: List[Message] = messages or []
        self._system_prompt: str = ""
    
    @property
    def system_prompt(self) -> str:
        return self._system_prompt
    
    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt
        if self.messages and self.messages[0].role == Role.SYSTEM:
            self.messages[0].content[0] = TextContent(text=prompt)
        else:
            self.messages.insert(0, Message.system(prompt))
    
    def add_user_message(
        self,
        text: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Message:
        message = Message.user(text, attachments or [])
        self.messages.append(message)
        return message
    
    def add_assistant_message(self, text: str) -> Message:
        message = Message.assistant(text)
        self.messages.append(message)
        return message
    
    def add_tool_result(
        self,
        tool_call_id: str,
        result: Any,
        is_error: bool = False
    ) -> Message:
        message = Message.tool_result(tool_call_id, result, is_error)
        self.messages.append(message)
        return message
    
    def get_last_message(self) -> Optional[Message]:
        return self.messages[-1] if self.messages else None
    
    def get_last_assistant_message(self) -> Optional[Message]:
        for msg in reversed(self.messages):
            if msg.role == Role.ASSISTANT:
                return msg
        return None
    
    def get_tool_calls_from_last_message(self) -> List[Dict[str, Any]]:
        last_msg = self.get_last_assistant_message()
        if not last_msg:
            return []
        
        calls = []
        for c in last_msg.content:
            if isinstance(c, ToolRequestContent):
                value = c.tool_call_value
                if value:
                    calls.append({
                        "id": c.id,
                        "name": value.name,
                        "arguments": value.arguments or {}
                    })
        return calls
    
    def to_provider_format(self) -> List[Dict[str, Any]]:
        result = []
        for msg in self.messages:
            if not msg.is_agent_visible:
                continue
            
            if msg.role == Role.SYSTEM:
                result.append({"role": "system", "content": msg.as_concat_text()})
            elif msg.role == Role.USER:
                result.append({"role": "user", "content": msg.as_concat_text()})
            elif msg.role == Role.ASSISTANT:
                tool_calls = []
                for c in msg.content:
                    if isinstance(c, ToolRequestContent):
                        value = c.tool_call_value
                        if value:
                            tool_calls.append({
                                "id": c.id,
                                "type": "function",
                                "function": {
                                    "name": value.name,
                                    "arguments": json.dumps(value.arguments or {})
                                }
                            })
                
                if tool_calls:
                    result.append({
                        "role": "assistant",
                        "content": msg.as_concat_text() or "",
                        "tool_calls": tool_calls
                    })
                else:
                    result.append({"role": "assistant", "content": msg.as_concat_text()})
            elif msg.role == Role.TOOL:
                for c in msg.content:
                    if isinstance(c, ToolResponseContent):
                        result.append({
                            "role": "tool",
                            "tool_call_id": c.id,
                            "content": json.dumps(c.content) if c.content else "Success",
                            "is_error": c.is_error
                        })
        return result
    
    def __iter__(self):
        return iter(self.messages)
    
    def __len__(self) -> int:
        return len(self.messages)
    
    def __repr__(self) -> str:
        return f"Conversation(messages={len(self.messages)})"
    
    def copy(self) -> "Conversation":
        return Conversation(messages=[Message.from_dict(m.to_dict()) for m in self.messages])
    
    def clear(self) -> None:
        system = self._system_prompt
        self.messages = []
        if system:
            self.set_system_prompt(system)
