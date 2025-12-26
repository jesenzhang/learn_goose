import logging
from typing import Optional, AsyncGenerator, Tuple

from ..session import SessionManager, Session
from ..conversation import Message, Role
from ..providers.base import Provider
from ..prompts import get_prompt_manager
from ..truncation import check_if_compaction_needed, compact_messages
from ..config import get_config

logger = logging.getLogger(__name__)

class Agent:
    def __init__(self, provider: Provider):
        self.provider = provider
        self.prompt_manager = get_prompt_manager()
        self.config = get_config()

    async def reply(self, session: Session, user_msg: Optional[Message] = None) -> AsyncGenerator[str, None]:
        """
        核心回复循环：用户输入 -> 检查上下文 -> (压缩) -> 渲染 Prompt -> 调用 LLM -> 流式输出
        """
        # 1. 如果有新消息，先存入数据库
        if user_msg:
            await SessionManager.add_message(session.id, user_msg)
        
        # 2. 获取当前完整的会话历史
        # 注意：这里获取的是数据库里的所有消息
        conversation = await SessionManager.get_conversation(session.id)
        
        # --- 核心逻辑：上下文压缩 ---
        # 检查是否超出了 Context Window (基于 session.total_tokens 或 估算)
        if await check_if_compaction_needed(self.provider, conversation, session.total_tokens):
            logger.info("Context limit reached. Compacting messages...")
            
            # 执行压缩 (这会调用 LLM 生成总结)
            compacted_conv, usage = await compact_messages(self.provider, conversation)
            
            # [关键步骤] 将压缩结果同步回数据库
            # 我们需要更新那些变为 "agent_invisible" 的旧消息，并插入新的 Summary
            await self._sync_compaction_to_db(session.id, conversation, compacted_conv)
            
            # 更新 session 的 token 统计 (加上总结消耗的 token)
            if usage.usage.total_tokens:
                 # 这里只是简单累加，实际可能需要更复杂的逻辑
                 pass 
            
            # 使用压缩后的对话继续
            conversation = compacted_conv

        # 3. 准备 Prompt
        # PromptManager 只需要处理 "Agent可见" 的消息
        visible_history = conversation.agent_visible_messages()
        
        # 渲染 (利用我们之前的 PromptManager)
        # 这里不需要再做 format_history 截断了，因为上面的 compaction 已经处理了
        messages_payload = self.prompt_manager.create_chat_completion_payload(
            system_template="system.md",
            user_template="task.md", # 或者根据情况为空
            history=visible_history,
            variables={
                "tools": self.config.extensions.get("tools", []), # 假设配置里有工具
                # ... 其他变量
            }
        )

        # 4. 调用 Provider 流式输出
        async for msg, usage in self.provider.stream("system_is_in_payload", messages_payload):
            if msg and msg.content:
                text = msg.as_concat_text()
                yield text
            
            # 5. 更新 Token 统计到数据库 (Session Loop 的最后一步)
            if usage:
                # TODO: 更新 session.total_tokens
                pass
                
        # TODO: 将 AI 的完整回复存入数据库 (accumulate logic)

    async def _sync_compaction_to_db(self, session_id: str, old_conv, new_conv):
        """
        将压缩后的状态变更写入数据库
        """
        # 1. 找出状态变更的消息 (从 visible -> invisible)
        for msg in new_conv.messages:
            if not msg.metadata.agent_visible:
                # 更新 DB 中的 metadata
                await SessionManager.update_message_metadata(session_id, msg.id, msg.metadata)
        
        # 2. 找出新增的消息 (Summary & Continuation)
        # 简单的做法是：ID 在 old_conv 里不存在的就是新的
        old_ids = {m.id for m in old_conv.messages if m.id}
        for msg in new_conv.messages:
            if msg.id and msg.id not in old_ids:
                await SessionManager.add_message(session_id, msg)
            elif not msg.id:
                # 没有 ID 的肯定是新生成的
                await SessionManager.add_message(session_id, msg)