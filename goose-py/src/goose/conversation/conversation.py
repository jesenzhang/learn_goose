from typing import List, Tuple, Optional, Set, Any
from pydantic import BaseModel, Field
from .message import (
    Message, MessageContent, Role, MessageMetadata,
    TextContent, ToolRequest, ToolResponse, 
    ThinkingContent, RedactedThinkingContent,
    FrontendToolRequest, ToolConfirmationRequest,
    ActionRequired
)

class InvalidConversation(Exception):
    def __init__(self, reason: str, conversation: "Conversation"):
        self.reason = reason
        self.conversation = conversation
        super().__init__(reason)

class Conversation(BaseModel):
    """
    对话容器，负责管理消息列表的视图和校验
    对应 Rust: pub struct Conversation(Vec<Message>)
    """
    messages: List[Message] = Field(default_factory=list)

    @classmethod
    def new_unvalidated(cls, messages: List[Message]) -> "Conversation":
        return cls(messages=messages)
    
    @classmethod
    def empty(cls) -> "Conversation":
        return cls(messages=[])

    def push(self, message: Message):
        """
        添加消息，如果可能则合并连续的文本消息。
        对应 Rust: pub fn push(&mut self, message: Message)
        """
        # 尝试合并逻辑：如果上一条消息 ID 相同，且都是纯文本，则合并文本
        if self.messages and self.messages[-1].id and self.messages[-1].id == message.id:
            last = self.messages[-1]
            last_content = last.content
            new_content = message.content
            
            # 检查是否都是单一文本节点
            if (len(last_content) == 1 and isinstance(last_content[0], TextContent) and
                len(new_content) == 1 and isinstance(new_content[0], TextContent)):
                # 合并文本
                last.content[0].text += new_content[0].text
            else:
                # 否则追加内容列表
                last.content.extend(new_content)
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
        """校验对话有效性"""
        _, issues = fix_messages(self.messages) # 使用副本检查
        if issues:
            raise InvalidConversation("\n".join(issues), self)
        return self

# --- The Fix Pipeline (核心修复逻辑) ---

def fix_conversation(conversation: Conversation) -> Tuple[Conversation, List[str]]:
    """
    准备发送给 LLM 的消息。过滤不可见消息，并修复逻辑错误。
    对应 Rust: pub fn fix_conversation(conversation: Conversation) -> (Conversation, Vec<String>)
    """
    all_msgs = conversation.messages
    
    # 1. Shadow Map: 区分可见与不可见
    # Rust Logic: 
    # enum MessageSlot { Visible(usize), NonVisible(Message) }
    # 这里的 usize 是 agent_visible_messages 的原始索引
    agent_visible_messages = []
    shadow_map = [] 
    
    for m in all_msgs:
        if m.metadata.agent_visible:
            idx = len(agent_visible_messages)
            agent_visible_messages.append(m.model_copy(deep=True))
            shadow_map.append(('visible', idx))
        else:
            shadow_map.append(('hidden', m))

    # 2. Fix Pipeline (只处理可见消息)
    fixed_visible, issues = fix_messages(agent_visible_messages)

    # 3. Reconstruct using shadow map
    # Rust Logic: Replace Visible slots with fixed messages using .get(idx)
    # 这意味着如果 fix 过程删除了消息，索引可能会前移，末尾的 Slot 会变成 None (被 drop)
    final_messages = []
    
    for type_, val in shadow_map:
        if type_ == 'visible':
            idx = val
            # 尝试从修正后的列表中获取对应索引的消息
            # 注意：Rust 的逻辑是 fixed_visible.get(idx)，这意味着它利用了
            # 列表紧缩后的索引。如果 visible 列表变短了，后面的 slot 就会拿不到消息而被丢弃。
            if idx < len(fixed_visible):
                final_messages.append(fixed_visible[idx])
        else:
            # NonVisible 直接保留
            final_messages.append(val)

    return Conversation(messages=final_messages), issues

def fix_messages(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """执行一系列修复步骤"""
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

# --- Individual Fixers ---

def merge_text_content_items(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """合并单条消息内部连续的 TextContent"""
    issues = []
    new_msgs = []
    for msg in messages:
        # 只处理 Assistant (Rust 逻辑: if msg.role != Role::Assistant { return msg })
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
        
        # 必须创建副本或者修改原对象 (这里假设 msg 是可变的)
        msg.content = new_content
        new_msgs.append(msg)
    return new_msgs, issues

def trim_assistant_text_whitespace(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """去除 Assistant 消息尾部的空白"""
    issues = []
    for msg in messages:
        if msg.role == Role.ASSISTANT:
            for item in msg.content:
                if isinstance(item, TextContent):
                    trimmed = item.text.rstrip()
                    if len(trimmed) != len(item.text):
                        item.text = trimmed
                        issues.append("Trimmed trailing whitespace from assistant message")
    return messages, issues

def remove_empty_messages(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """移除没有任何内容的消息"""
    new_msgs = []
    issues = []
    for msg in messages:
        is_empty = True
        # 只要有一个非空文本或非文本内容，就算非空
        for item in msg.content:
            if isinstance(item, TextContent):
                if item.text: # 非空字符串
                    is_empty = False
                    break
            else:
                # 任何非文本内容 (ToolRequest, Image 等) 都视为有内容
                is_empty = False
                break
        
        if is_empty:
            issues.append("Removed empty message")
        else:
            new_msgs.append(msg)
    return new_msgs, issues

def fix_tool_calling(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """
    核心修复逻辑 (对应 Rust: fix_tool_calling)
    """
    issues = []
    pending_tool_requests: Set[str] = set()
    
    # 必须深拷贝，因为我们会修改 content
    # Python 列表修改比较麻烦，我们采用两轮扫描
    
    # Pass 1: Scan and cleanup obvious errors, track pending requests
    for msg in messages:
        to_remove = []
        
        if msg.role == Role.USER:
            for idx, content in enumerate(msg.content):
                if isinstance(content, (ToolRequest, FrontendToolRequest)):
                    to_remove.append(idx)
                    # 尝试获取 id 用于 issue 描述
                    req_id = getattr(content, 'id', 'unknown')
                    issues.append(f"Removed tool request '{req_id}' from user message")
                
                elif isinstance(content, ToolConfirmationRequest):
                    to_remove.append(idx)
                    issues.append(f"Removed tool confirmation request '{content.tool_name}' from user message")
                
                elif isinstance(content, (ThinkingContent, RedactedThinkingContent)):
                    to_remove.append(idx)
                    issues.append("Removed thinking content from user message")
                
                elif isinstance(content, ToolResponse):
                    # 检查是否是 pending 的响应
                    if content.id in pending_tool_requests:
                        pending_tool_requests.remove(content.id)
                    else:
                        to_remove.append(idx)
                        issues.append(f"Removed orphaned tool response '{content.id}'")
        
        elif msg.role == Role.ASSISTANT:
            for idx, content in enumerate(msg.content):
                if isinstance(content, ToolResponse):
                    to_remove.append(idx)
                    issues.append(f"Removed tool response '{content.id}' from assistant message")
                
                elif isinstance(content, FrontendToolRequest):
                    to_remove.append(idx)
                    req_id = getattr(content.tool_call, 'name', 'unknown')
                    issues.append(f"Removed frontend tool request '{req_id}' from assistant message")

                elif isinstance(content, ToolRequest):
                    pending_tool_requests.add(content.id)
        
        # 执行删除 (倒序)
        for idx in sorted(to_remove, reverse=True):
            msg.content.pop(idx)

    # Pass 2: Remove orphaned ToolRequests (requests that got no response)
    # Rust Logic: 再次遍历，如果是 Assistant 的 ToolRequest 且 id 仍在 pending_tool_requests 中，则移除
    if pending_tool_requests:
        for msg in messages:
            if msg.role == Role.ASSISTANT:
                to_remove = []
                for idx, content in enumerate(msg.content):
                    if isinstance(content, ToolRequest):
                        if content.id in pending_tool_requests:
                            to_remove.append(idx)
                            issues.append(f"Removed orphaned tool request '{content.id}'")
                
                for idx in sorted(to_remove, reverse=True):
                    msg.content.pop(idx)

    # Clean up potentially empty messages after removal
    return remove_empty_messages(messages)

def merge_consecutive_messages(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """合并连续的同有效角色(Effective Role)消息"""
    if not messages:
        return [], []
        
    merged = []
    issues = []
    
    for msg in messages:
        if not merged:
            merged.append(msg)
            continue
            
        last = merged[-1]
        
        # 使用 Effective Role 判断
        # Rust: if effective_role(last) == effective_role(msg)
        role_last = _effective_role(last)
        role_curr = _effective_role(msg)
        
        if role_last == role_curr:
            # 合并
            last.content.extend(msg.content)
            issues.append(f"Merged consecutive {role_curr} messages")
        else:
            merged.append(msg)
            
    return merged, issues

def _has_tool_response(message: Message) -> bool:
    return any(isinstance(c, ToolResponse) for c in message.content)

def _effective_role(message: Message) -> str:
    """
    Rust: effective_role
    如果 User 消息包含 ToolResponse，视为 "tool" 角色，避免与普通 User 文本合并
    """
    if message.role == Role.USER and _has_tool_response(message):
        return "tool"
    return message.role.value

def fix_lead_trail(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    """
    确保对话以 User 开始，不以 Assistant 结束
    Rust: fix_lead_trail
    """
    issues = []
    if not messages:
        return messages, issues
        
    # Remove leading Assistant
    if messages[0].role == Role.ASSISTANT:
        messages.pop(0)
        issues.append("Removed leading assistant message")
    
    if not messages:
        return messages, issues

    # Remove trailing Assistant
    if messages[-1].role == Role.ASSISTANT:
        messages.pop()
        issues.append("Removed trailing assistant message")
        
    return messages, issues

def populate_if_empty(messages: List[Message]) -> Tuple[List[Message], List[str]]:
    issues = []
    if not messages:
        # Rust: const PLACEHOLDER_USER_MESSAGE: &str = "Hello";
        messages.append(Message.user("Hello"))
        issues.append("Added placeholder user message to empty conversation")
    return messages, issues