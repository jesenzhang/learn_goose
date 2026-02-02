"""
Truncation Integration for Conversation

将 Truncation 功能集成到 Assistant 的 Conversation 类中
"""

import logging
from typing import Any, Dict, List, Optional
from . import TruncationManager, TruncationConfig

logger = logging.getLogger(__name__)

class ConversationTruncationMixin:
    """
    Mixin 类，为 Conversation 添加 Truncation 能力

    使用方式：
    class Conversation(ConversationTruncationMixin):
        ...
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._truncation_manager: Optional[TruncationManager] = None
        self._last_compaction_summary: Optional[str] = None

    def set_truncation_manager(self, manager: TruncationManager):
        """设置 Truncation 管理器"""
        self._truncation_manager = manager

    def get_truncation_manager(self) -> Optional[TruncationManager]:
        """获取 Truncation 管理器"""
        return self._truncation_manager

    def messages_to_dict(self) -> List[Dict[str, Any]]:
        """
        将 Message 对象列表转换为字典列表
        用于 Truncation 处理
        """
        result = []
        # 获取所有消息（包括临时消息）
        all_messages = []
        if hasattr(self, '_ephemeral_messages'):
            all_messages.extend(self._ephemeral_messages)
        if hasattr(self, 'messages'):
            all_messages.extend(self.messages)

        for msg in all_messages:
            msg_dict = {
                "role": msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                "content": []
            }

            for content in msg.content:
                if hasattr(content, 'model_dump'):
                    msg_dict["content"].append(content.model_dump())
                else:
                    msg_dict["content"].append(str(content))

            result.append(msg_dict)

        return result

    def apply_compaction(self, compacted_messages: List[Dict[str, Any]]):
        """
        应用压缩结果到 Conversation

        Args:
            compacted_messages: 压缩后的消息字典列表
        """
        # 清空现有消息
        self.messages.clear()

        # 将压缩后的消息字典转换回 Message 对象
        # 注意：这里需要导入 Conversation 模块中的类
        try:
            from ..conversation import Message, Role
            from ..conversation.message import TextContent, MessageVisible

            for msg_dict in compacted_messages:
                role_str = msg_dict.get("role", "user")
                # 处理 role 可能是枚举或字符串
                if isinstance(role_str, str):
                    if role_str == "system":
                        role = Role.SYSTEM
                    elif role_str == "assistant":
                        role = Role.ASSISTANT
                    elif role_str == "user":
                        role = Role.USER
                    else:
                        role = Role.USER
                else:
                    role = role_str

                # 构建消息内容
                content_list = []
                content = msg_dict.get("content", "")

                if isinstance(content, str):
                    content_list.append(TextContent(text=content))
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict):
                            if c.get("type") == "text":
                                content_list.append(TextContent(text=c.get("text", "")))
                            else:
                                content_list.append(TextContent(text=str(c)))
                        else:
                            content_list.append(TextContent(text=str(c)))
                else:
                    content_list.append(TextContent(text=str(content)))

                # 获取元数据
                metadata = msg_dict.get("metadata", {}) or {}

                # 创建消息
                message = Message(role=role, content=content_list)
                # 保留元数据（用于标记 summary/continuation）
                if metadata:
                    message.metadata = dict(metadata)

                # 设置可见性
                if metadata:
                    if "agent_visible" in metadata or "user_visible" in metadata:
                        message.visible = MessageVisible(
                            agent_visible=metadata.get("agent_visible", True),
                            user_visible=metadata.get("user_visible", True)
                        )

                self.messages.append(message)
        except Exception as e:
            logger.error(f"Failed to apply compaction: {e}", exc_info=True)

    async def check_and_apply_truncation(
        self,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        检查并应用消息压缩

        Args:
            system_prompt: 系统提示词
            tools: 工具定义列表

        Returns:
            是否执行了压缩
        """
        if not self._truncation_manager:
            return False

        # 转换消息为字典格式
        messages_dict = self.messages_to_dict()

        # 检查并压缩
        compacted, usage_info = await self._truncation_manager.check_and_compact(
            messages=messages_dict,
            system_prompt=system_prompt,
        )

        if compacted:
            # 获取压缩结果
            result = await self._truncation_manager.compactor.compact_messages(
                conversation_messages=messages_dict,
                system_prompt=system_prompt,
                is_manual=False,
            )

            # 应用压缩
            if result.success and result.compacted_message_count < len(messages_dict):
                self._last_compaction_summary = result.summary
                compacted_messages = self._truncation_manager.compactor._create_compacted_conversation(
                    messages_dict,
                    result.summary,
                    is_manual=False,
                )
                self.apply_compaction(compacted_messages)
                logger.info(f"Truncation applied: {len(messages_dict)} -> {len(compacted_messages)} messages")
                return True

        return False

    def get_last_compaction_summary(self) -> Optional[str]:
        """Return latest compaction summary (if any)."""
        return self._last_compaction_summary

    def estimate_context_usage(
        self,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        估算当前上下文使用情况

        Args:
            system_prompt: 系统提示词
            tools: 工具定义列表

        Returns:
            使用情况字典，如果没有 Truncation 管理器则返回 None
        """
        if not self._truncation_manager:
            return None

        messages_dict = self.messages_to_dict()
        return self._truncation_manager.estimate_context_usage(
            messages=messages_dict,
            tools=tools or [],
            system_prompt=system_prompt,
        )


__all__ = [
    "ConversationTruncationMixin",
]
