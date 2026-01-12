from typing import List, Tuple, Set, Optional, Any
from pydantic import BaseModel, Field
from .message import (
    Message, MessageContent, Role, MessageMetadata,
    TextContent, ToolRequest, ToolResponse, 
    ThinkingContent, RedactedThinkingContent,
    FrontendToolRequest, ToolConfirmationRequest,
    ActionRequired, SystemNotification
)

class InvalidConversation(Exception):
    def __init__(self, reason: str, conversation: "Conversation"):
        self.reason = reason
        self.conversation = conversation
        super().__init__(reason)

class Conversation(BaseModel):
    messages: List[Message] = Field(default_factory=list)

    @classmethod
    def new_unvalidated(cls, messages: List[Message]) -> "Conversation":
        return cls(messages=messages)
    
    @classmethod
    def empty(cls) -> "Conversation":
        return cls(messages=[])

    def push(self, message: Message):
        """Rust: pub fn push(&mut self, message: Message)"""
        if self.messages and self.messages[-1].id and self.messages[-1].id == message.id:
            last = self.messages[-1]
            if (len(last.content) == 1 and isinstance(last.content[0], TextContent) and
                len(message.content) == 1 and isinstance(message.content[0], TextContent)):
                last.content[0].text += message.content[0].text
            else:
                last.content.extend(message.content)
        else:
            self.messages.append(message)

    def extend(self, messages: List[Message]):
        for msg in messages:
            self.push(msg)

    def agent_visible_messages(self) -> List[Message]:
        return [m for m in self.messages if m.metadata.agent_visible]

    def user_visible_messages(self) -> List[Message]:
        return [m for m in self.messages if m.metadata.user_visible]
    
    def last(self) -> Optional[Message]:
        return self.messages[-1] if self.messages else None

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
        if m.metadata.agent_visible:
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