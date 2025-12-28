import logging
from typing import List
from ..conversation.message import (
    Message, Role, SystemNotification, SystemNotificationType, MessageMetadata
)
from ..utils.token_counter import count_history_tokens, estimate_tokens

logger = logging.getLogger("goose.truncation")

class ContextTruncator:
    def __init__(self, max_tokens: int = 16000, keep_last_messages: int = 10):
        """
        :param max_tokens: 发送给 LLM 的最大 Token 上限 (包含 System Prompt)
        :param keep_last_messages: 无论如何都要保留的最近消息条数 (防止破坏短期记忆)
        """
        self.max_tokens = max_tokens
        self.keep_last_messages = keep_last_messages

    def truncate(self, messages: List[Message], system_prompt: str = "") -> List[Message]:
        """
        输入完整历史，返回一个 Token 数合规的子集列表。
        """
        # 1. 估算总负载
        total_tokens = count_history_tokens(messages)
        system_tokens = estimate_tokens(system_prompt)
        current_load = total_tokens + system_tokens
        
        # 如果未超标，直接返回原列表
        if current_load <= self.max_tokens:
            return messages

        logger.info(f"Context limit exceeded ({current_load}/{self.max_tokens}). Truncating...")

        # 2. 保护最近的消息
        if len(messages) <= self.keep_last_messages:
            logger.warning("History is too short to truncate safely. Sending as is (risk of overflow).")
            return messages

        # 分离出不可动摇的近期消息 (Tail) 和 较早的消息 (Head)
        recent_messages = messages[-self.keep_last_messages:]
        older_messages = messages[:-self.keep_last_messages]
        
        # 计算近期消息的开销
        recent_load = count_history_tokens(recent_messages)
        remaining_budget = self.max_tokens - system_tokens - recent_load
        
        if remaining_budget < 0:
            logger.warning("Recent messages alone exceed the limit! Truncating recent messages is not implemented yet.")
            # 极端情况：哪怕只留最近10条都超了，那只能硬着头皮发，或者进一步减少 keep_last_messages
            return recent_messages

        # 3. 逐步丢弃较早的消息
        # 我们将 older_messages 中能够塞进 remaining_budget 的部分保留下来 (取尾部)
        
        preserved_older = []
        dropped_count = 0
        
        # 倒序遍历 (从较新的旧消息开始尝试保留)
        current_older_tokens = 0
        for msg in reversed(older_messages):
            msg_tokens = count_history_tokens([msg]) # 计算单条
            if current_older_tokens + msg_tokens <= remaining_budget:
                preserved_older.insert(0, msg)
                current_older_tokens += msg_tokens
            else:
                # 一旦装不下了，前面的更旧的消息肯定也都不要了
                dropped_count = len(older_messages) - len(preserved_older)
                break
        
        # 4. 插入摘要/占位符
        if dropped_count > 0:
            logger.info(f"Dropped {dropped_count} early messages to fit token limit.")
            
            # 使用 SystemNotification 告知 LLM 发生了截断
            notification = Message(
                role=Role.SYSTEM,
                content=[SystemNotification(
                    notificationType=SystemNotificationType.INLINE,
                    msg=f"[System: Flattened {dropped_count} early messages to save context space. Previous context is summarized or omitted.]"
                )],
                # 标记为对用户不可见 (可选，看前端需求)
                metadata=MessageMetadata(userVisible=False, agentVisible=True)
            )
            
            # 最终组合: [System Notification] + [Preserved Old] + [Recent]
            return [notification] + preserved_older + recent_messages
        
        return messages