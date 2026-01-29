from typing import List, Tuple, Set, Optional, Any, Dict
from pydantic import BaseModel, Field, PrivateAttr
from .message import (
    Message, MessageContent, Role, MessageVisible,
    TextContent, ToolRequest, ToolResponse,
    ThinkingContent, RedactedThinkingContent,
    FrontendToolRequest, ToolConfirmationRequest,
    ActionRequired, SystemNotification
)

# 导入 Truncation Mixin
try:
    from ..truncation.conversation_integration import ConversationTruncationMixin
    _TRUNCATION_AVAILABLE = True
except ImportError:
    _TRUNCATION_AVAILABLE = False
    ConversationTruncationMixin = object  # 降级为空类

class InvalidConversation(Exception):
    def __init__(self, reason: str, conversation: "Conversation"):
        self.reason = reason
        self.conversation = conversation
        super().__init__(reason)

class Conversation(ConversationTruncationMixin, BaseModel):
    """
    增强版 Conversation 类，支持双流消息管理：

    1. **持久化消息流 (messages)**: 需要保存到数据库的消息
       - 用户输入、助手回复、工具调用和响应

    2. **临时消息流 (_ephemeral_messages)**: 仅用于本次推理的临时消息
       - 系统提示词、意图指令、Deep Thinking 指令等
    """
    # 持久化消息 - 需要保存到数据库
    messages: List[Message] = Field(default_factory=list)

    # 临时消息 - 仅用于推理，不保存到数据库
    # 使用 PrivateAttr 避免序列化到数据库
    _ephemeral_messages: List[Message] = PrivateAttr(default_factory=list)

    @classmethod
    def new_unvalidated(cls, messages: List[Message]) -> "Conversation":
        return cls(messages=messages)

    @classmethod
    def empty(cls) -> "Conversation":
        return cls(messages=[])

    def push(self, message: Message, ephemeral: bool = False):
        """
        推送消息到会话

        Args:
            message: 要添加的消息
            ephemeral: 是否为临时消息（不保存到数据库）
        """
        target_list = self._ephemeral_messages if ephemeral else self.messages

        if target_list and target_list[-1].id and target_list[-1].id == message.id:
            last = target_list[-1]
            if (len(last.content) == 1 and isinstance(last.content[0], TextContent) and
                len(message.content) == 1 and isinstance(message.content[0], TextContent)):
                last.content[0].text += message.content[0].text
            else:
                last.content.extend(message.content)
        else:
            target_list.append(message)

    def extend(self, messages: List[Message], ephemeral: bool = False):
        """批量推送消息

        Args:
            messages: 消息列表
            ephemeral: 是否为临时消息（不保存到数据库）
        """
        for msg in messages:
            self.push(msg, ephemeral=ephemeral)

    def pop_last_ephemeral(self) -> Optional[Message]:
        """弹出最后的临时消息"""
        if self._ephemeral_messages:
            return self._ephemeral_messages.pop()
        return None

    def clear_ephemeral(self):
        """清空所有临时消息"""
        self._ephemeral_messages.clear()

    def update_system_prompt(self, system_prompt: str):
        """
        更新或创建系统提示词（临时消息）

        系统提示词总是作为临时消息，且位于最前面
        """
        system_msg = Message.system(system_prompt)
        system_msg.visible = MessageVisible(user_visible=False, agent_visible=True)

        # 检查是否已有系统消息
        for i, msg in enumerate(self._ephemeral_messages):
            if msg.role == Role.SYSTEM:
                self._ephemeral_messages[i] = system_msg
                return

        # 没有系统消息，插入到最前面
        self._ephemeral_messages.insert(0, system_msg)

    def agent_visible_messages(self) -> List[Message]:
        """获取所有 agent 可见的消息（包括临时消息）"""
        all_messages = self._ephemeral_messages + self.messages
        return [m for m in all_messages if m.visible.agent_visible]

    def user_visible_messages(self) -> List[Message]:
        """获取所有用户可见的消息（不包括临时消息）"""
        return [m for m in self.messages if m.visible.user_visible]

    def last(self) -> Optional[Message]:
        """获取最后一条持久化消息"""
        return self.messages[-1] if self.messages else None

    def for_llm(self, deep_thinking: bool = False, deep_thinking_instruction: str = None) -> List[Message]:
        """
        生成用于 LLM 推理的消息列表

        Args:
            deep_thinking: 是否启用深度思考模式
            deep_thinking_instruction: 深度思考指令（如果启用）

        Returns:
            合并后的消息列表（临时消息在前，持久化消息在后）
        """
        result = []

        # 1. 添加临时消息（系统提示词等）
        result.extend(self._ephemeral_messages)

        # 2. 添加持久化消息
        if deep_thinking and self.messages:
            # Deep Thinking 模式下，修改最后一条 User 消息
            for i, msg in enumerate(self.messages):
                if i == len(self.messages) - 1 and msg.role == Role.USER and deep_thinking_instruction:
                    # 创建修改后的消息副本，注入 Deep Thinking 指令
                    modified_content = []
                    for c in msg.content:
                        if isinstance(c, TextContent):
                            modified_content.append(TextContent(text=c.text + deep_thinking_instruction))
                        else:
                            modified_content.append(c)
                    result.append(Message(role=Role.USER, content=modified_content, metadata=msg.metadata, visible=msg.visible))
                else:
                    result.append(msg)
        else:
            result.extend(self.messages)

        return result

    def pending_messages(self) -> List[Message]:
        """
        获取尚未持久化到数据库的消息

        Returns:
            需要保存到数据库的消息列表
        (注意：这里返回所有持久化消息，实际保存时应该只保存新增的消息)
        """
        return self.messages

    def validate(self) -> "Conversation":
        _, issues = fix_messages(self.messages)
        if issues:
            raise InvalidConversation("\n".join(issues), self)
        return self

# --- Fix Pipeline ---

def fix_conversation(conversation: Conversation) -> Tuple[Conversation, List[str]]:
    """
    对应 Rust: fix_conversation
    Shadow Map 策略: 
    保留不可见消息的位置，仅修复可见消息序列，然后重建列表。
    """
    all_msgs = conversation.messages
    
    # 1. 构建 Shadow Map
    # 'v' = slot for visible message, ('h', msg) = hidden message
    shadow_map = [] 
    agent_visible_messages = []
    
    for m in all_msgs:
        if m.visible.agent_visible:
            shadow_map.append('v')
            agent_visible_messages.append(m.model_copy(deep=True))
        else:
            shadow_map.append(('h', m))

    # 2. 修复可见消息
    fixed_visible, issues = fix_messages(agent_visible_messages)

    # 3. 重建列表 (Queue Consumption 模式)
    final_messages = []
    visible_iter = iter(fixed_visible)
    
    for slot in shadow_map:
        if slot == 'v':
            try:
                # 尝试填入一个修复后的可见消息
                # 如果因为合并/删除导致可见消息变少，后续的 'v' 槽位将被跳过
                msg = next(visible_iter)
                final_messages.append(msg)
            except StopIteration:
                pass
        else:
            # ('h', msg) -> 直接保留隐藏消息
            final_messages.append(slot[1])

    # 注意：理论上 fixed_visible 可能会因为 populate_if_empty 变长（极少），
    # 如果变长了，多出来的消息应该追加到末尾。
    # Rust 的实现比较隐晦，但通常 fix_conversation 用于 snapshot 生成，追加到末尾是安全的。
    for remaining_msg in visible_iter:
        final_messages.append(remaining_msg)

    return Conversation(messages=final_messages), issues

def fix_messages(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    processors = [
        merge_text_content_items,
        trim_assistant_text_whitespace,
        remove_empty_messages,
        fix_tool_calling,
        merge_consecutive_messages,
        fix_lead_trail,
        populate_if_empty
    ]
    
    current_msgs = messages
    all_issues = []
    
    for proc in processors:
        current_msgs, issues = proc(current_msgs)
        all_issues.extend(issues)
        
    return current_msgs, all_issues

# --- Fixers ---

def merge_text_content_items(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    issues = []
    new_msgs = []
    for msg in messages:
        if msg.role != Role.ASSISTANT:
            new_msgs.append(msg)
            continue
            
        new_content = []
        for item in msg.content:
            if isinstance(item, TextContent):
                if new_content and isinstance(new_content[-1], TextContent):
                    new_content[-1].text += item.text
                else:
                    new_content.append(item)
            else:
                new_content.append(item)
        
        if len(new_content) != len(msg.content):
            issues.append("Merged text content")
        
        msg.content = new_content
        new_msgs.append(msg)
    return new_msgs, issues

def trim_assistant_text_whitespace(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    issues = []
    for msg in messages:
        if msg.role == Role.ASSISTANT:
            for item in msg.content:
                if isinstance(item, TextContent) and item.text:
                    trimmed = item.text.rstrip()
                    if len(trimmed) != len(item.text):
                        item.text = trimmed
                        issues.append("Trimmed trailing whitespace")
    return messages, issues

def remove_empty_messages(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    new_msgs = []
    issues = []
    for msg in messages:
        is_empty = True
        for item in msg.content:
            if isinstance(item, TextContent):
                if item.text and item.text.strip(): # Rust logic might imply non-empty
                    is_empty = False
                    break
            else:
                is_empty = False
                break
        
        if is_empty:
            issues.append("Removed empty message")
        else:
            new_msgs.append(msg)
    return new_msgs, issues

def fix_tool_calling(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    issues = []
    pending_tool_requests: Set[str] = set()
    
    # Pass 1
    for msg in messages:
        to_remove = []
        if msg.role == Role.USER:
            for idx, content in enumerate(msg.content):
                if isinstance(content, (ToolRequest, FrontendToolRequest)):
                    to_remove.append(idx)
                    issues.append("Removed tool request from user")
                elif isinstance(content, ToolConfirmationRequest):
                    to_remove.append(idx)
                    issues.append("Removed tool confirmation from user")
                elif isinstance(content, (ThinkingContent, RedactedThinkingContent)):
                    to_remove.append(idx)
                    issues.append("Removed thinking from user")
                elif isinstance(content, ToolResponse):
                    if content.id in pending_tool_requests:
                        pending_tool_requests.remove(content.id)
                    else:
                        to_remove.append(idx)
                        issues.append(f"Removed orphaned tool response {content.id}")
        
        elif msg.role == Role.ASSISTANT:
            for idx, content in enumerate(msg.content):
                if isinstance(content, ToolResponse):
                    to_remove.append(idx)
                    issues.append("Removed tool response from assistant")
                elif isinstance(content, ToolRequest):
                    pending_tool_requests.add(content.id)
        
        for idx in sorted(to_remove, reverse=True):
            msg.content.pop(idx)

    # Pass 2: Remove orphaned requests
    if pending_tool_requests:
        for msg in messages:
            if msg.role == Role.ASSISTANT:
                to_remove = []
                for idx, content in enumerate(msg.content):
                    if isinstance(content, ToolRequest):
                        if content.id in pending_tool_requests:
                            to_remove.append(idx)
                            issues.append(f"Removed orphaned tool request {content.id}")
                for idx in sorted(to_remove, reverse=True):
                    msg.content.pop(idx)

    return remove_empty_messages(messages)

def merge_consecutive_messages(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    if not messages: return [], []
    merged = []
    issues = []
    
    for msg in messages:
        if not merged:
            merged.append(msg)
            continue
        last = merged[-1]
        
        role_last = _effective_role(last)
        role_curr = _effective_role(msg)
        
        if role_last == role_curr:
            last.content.extend(msg.content)
            issues.append(f"Merged consecutive {role_curr} messages")
        else:
            merged.append(msg)
            
    return merged, issues

def _has_tool_response(message: Message) -> bool:
    return any(isinstance(c, ToolResponse) for c in message.content)

def _effective_role(message: Message) -> str:
    if message.role == Role.USER and _has_tool_response(message):
        return "tool"
    return message.role.value

def fix_lead_trail(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    issues = []
    if not messages: return messages, issues
    
    if messages[0].role == Role.ASSISTANT:
        messages.pop(0)
        issues.append("Removed leading assistant")
    
    if not messages: return messages, issues

    if messages[-1].role == Role.ASSISTANT:
        messages.pop()
        issues.append("Removed trailing assistant")
        
    return messages, issues

def populate_if_empty(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    issues = []
    if not messages:
        messages.append(Message.user("Hello"))
        issues.append("Added placeholder user message")
    return messages, issues

def get_last_assistant_message(conversation: "Conversation") -> Optional[Message]:
    """获取最后一条助手消息"""
    for msg in reversed(conversation.messages):
        if msg.role == Role.ASSISTANT:
            return msg
    return None

def get_tool_calls_from_last_message(conversation: "Conversation") -> List[Dict[str, Any]]:
    """从最后一条助手消息获取工具调用"""
    last_msg = get_last_assistant_message(conversation)
    if not last_msg:
        return []

    calls = []
    for c in last_msg.content:
        if isinstance(c, ToolRequest):
            if hasattr(c, 'tool_call'):
                tool_call = c.tool_call
                if hasattr(tool_call, 'value') and tool_call.value:
                    calls.append({
                        "id": c.id,
                        "name": tool_call.value.name if hasattr(tool_call.value, 'name') else "",
                        "arguments": tool_call.value.arguments if hasattr(tool_call.value, 'arguments') else {}
                    })
    return calls

def to_provider_format(conversation: "Conversation") -> List[Dict[str, Any]]:
    """将 Conversation 转换为 Provider 格式"""
    result = []
    for msg in conversation.messages:
        if not msg.visible_to_agent:
            continue

        if msg.role == Role.SYSTEM:
            result.append({"role": "system", "content": msg.text})
        elif msg.role == Role.USER:
            result.append({"role": "user", "content": msg.text})
        elif msg.role == Role.ASSISTANT:
            tool_calls = []
            for c in msg.content:
                if isinstance(c, ToolRequest):
                    if hasattr(c, 'tool_call'):
                        tool_call = c.tool_call
                        if hasattr(tool_call, 'value') and tool_call.value:
                            tool_calls.append({
                                "id": c.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.value.name if hasattr(tool_call.value, 'name') else "",
                                    "arguments": json.dumps(tool_call.value.arguments if hasattr(tool_call.value, 'arguments') else {})
                                }
                            })

            if tool_calls:
                result.append({
                    "role": "assistant",
                    "content": msg.text or "",
                    "tool_calls": tool_calls
                })
            else:
                result.append({"role": "assistant", "content": msg.text or ""})
        elif msg.role == Role.TOOL:
            for c in msg.content:
                if isinstance(c, ToolResponse):
                    if hasattr(c, 'tool_result'):
                        tr = c.tool_result
                        content_text = ""
                        if hasattr(tr, 'content'):
                            texts = []
                            for item in tr.content:
                                if hasattr(item, 'text') and item.text:
                                    texts.append(item.text)
                                elif isinstance(item, dict):
                                    texts.append(str(item))
                                else:
                                    texts.append(str(item))
                            content_text = "\n".join(texts)
                        elif not content_text:
                            content_text = "Success"

                        result.append({
                            "role": "tool",
                            "tool_call_id": c.id,
                            "content": content_text,
                            "is_error": tr.is_error if hasattr(tr, 'is_error') else False
                        })
    return result

