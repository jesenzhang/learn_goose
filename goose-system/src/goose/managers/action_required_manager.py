"""
Action Required Manager

处理需要用户操作的消息，包括工具确认和征询。
参考 goose-rs/crates/goose/src/action_required_manager.rs 实现。
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid

from ..conversation.message import Message, Role, ActionRequiredContent

logger = logging.getLogger("goose.managers.action_required_manager")


class PendingRequest:
    """待处理的请求"""

    def __init__(self, response_future: asyncio.Future):
        self.response_future = response_future
        self.created_at = datetime.now()


class ActionRequiredManager:
    """
    Action Required Manager

    处理需要用户操作的消息，包括：
    - tool_confirmation: 工具确认
    - elicitation: 征询用户信息
    - elicitation_response: 征询响应
    """

    _instance: Optional["ActionRequiredManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._pending: Dict[str, PendingRequest] = {}
        self._request_queue: asyncio.Queue[Message] = asyncio.Queue()
        self._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "ActionRequiredManager":
        """获取全局单例实例"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def global_sync(cls) -> "ActionRequiredManager":
        """获取全局单例实例（同步）"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def request_and_wait(
        self,
        message: str,
        schema: Dict[str, Any],
        timeout_seconds: float = 60.0
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
       请求用户输入并等待响应

        Args:
            message: 显示给用户的消息
            schema: JSON Schema 定义期望的输入格式
            timeout_seconds: 超时时间（秒）

        Returns:
            (success, user_data) 元组，成功时 user_data 包含用户输入
        """
        request_id = str(uuid.uuid4())

        # 创建 future 用于接收响应
        response_future: asyncio.Future[Dict[str, Any]] = asyncio.Future()

        # 存储待处理请求
        async with self._lock:
            self._pending[request_id] = PendingRequest(response_future)

        # 创建 elicitation 消息
        action_required_message = Message.assistant().with_action_required_elicitation(
            action_id=request_id,
            message=message,
            requested_schema=schema
        )

        # 发送消息到队列
        try:
            self._request_queue.put_nowait(action_required_message)
        except asyncio.QueueFull:
            logger.warning("Action required queue full, cannot send message")
            async with self._lock:
                self._pending.pop(request_id, None)
            return False, None

        # 等待响应或超时
        try:
            user_data = await asyncio.wait_for(response_future, timeout=timeout_seconds)
            return True, user_data
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response: {request_id}")
            async with self._lock:
                self._pending.pop(request_id, None)
            return False, None
        except asyncio.CancelledError:
            logger.warning(f"Request cancelled: {request_id}")
            async with self._lock:
                self._pending.pop(request_id, None)
            return False, None

    async def request_tool_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        prompt: Optional[str] = None,
            timeout_seconds: float = 60.0
    ) -> Tuple[bool, Optional[bool]]:
        """
        请求工具确认

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            prompt: 显示给用户的提示
            timeout_seconds: 超时时间（秒）

        Returns:
            (success, approved) 元组，成功时 approved 表示是否批准
        """
        request_id = str(uuid.uuid4())

        # 创建 future 用于接收响应
        response_future: asyncio.Future[Dict[str, Any]] = asyncio.Future()

        # 存储待处理请求
        async with self._lock:
            self._pending[request_id] = PendingRequest(response_future)

        # 创建 tool confirmation 消息
        action_required_message = Message.assistant().with_action_required_tool_confirmation(
            action_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            prompt=prompt
        )

        # 发送消息到队列
        try:
            self._request_queue.put_nowait(action_required_message)
        except asyncio.QueueFull:
            logger.warning("Action required queue full, cannot send message")
            async with self._lock:
                self._pending.pop(request_id, None)
            return False, None

        # 等待响应或超时
        try:
            user_data = await asyncio.wait_for(response_future, timeout=timeout_seconds)
            # user_data 应该包含 approved 字段
            approved = user_data.get("approved", False)
            return True, approved
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for tool confirmation: {request_id}")
            async with self._lock:
                self._pending.pop(request_id, None)
            return False, None
        except asyncio.CancelledError:
            logger.warning(f"Tool confirmation cancelled: {request_id}")
            async with self._lock:
                self._pending.pop(request_id, None)
            return False, None

    async def submit_response(
        self,
        request_id: str,
        user_data: Dict[str, Any]
    ) -> bool:
        """
        提交用户响应

        Args:
            request_id: 请求 ID
            user_data: 用户提供的数据

        Returns:
            是否成功提交响应
        """
        async with self._lock:
            pending = self._pending.get(request_id)

            if pending is None:
                logger.warning(f"Request not found: {request_id}")
                return False

            # 检查 future 是否已完成
            if pending.response_future.done():
                logger.warning(f"Future already done for request: {request_id}")
                return False

            # 设置结果
            try:
                pending.response_future.set_result(user_data)
                self._pending.pop(request_id)
                return True
            except asyncio.InvalidStateError:
                logger.warning(f"Invalid state when setting result for request: {request_id}")
                return False

    async def get_pending_message(self) -> Optional[Message]:
        """
        从队列中获取待处理的消息

        Returns:
            下一个待处理的消息，如果没有则返回 None
        """
        try:
            return await asyncio.wait_for(self._request_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

    async def get_all_pending_messages(self) -> list[Message]:
        """
        获取队列中所有待处理的消息（非阻塞）

        Returns:
            所有待处理的消息列表
        """
        messages = []
        while not self._request_queue.empty():
            try:
                msg = self._request_queue.get_nowait()
                messages.append(msg)
            except asyncio.QueueEmpty:
                break
        return messages

    async def cancel_request(self, request_id: str) -> bool:
        """
        取消待处理的请求

        Args:
            request_id: 请求 ID

        Returns:
            是否成功取消
        """
        async with self._lock:
            pending = self._pending.get(request_id)

            if pending is None:
                return False

            if not pending.response_future.cancelled():
                pending.response_future.cancel()

            self._pending.pop(request_id)
            return True

    async def cleanup_expired(self, timeout_seconds: float = 300.0) -> int:
        """
        清理过期的请求

        Args:
            timeout_seconds: 超时阈值（秒）

        Returns:
            清理的请求数量
        """
        now = datetime.now()
        expired_ids = []

        async with self._lock:
            for request_id, pending in self._pending.items():
                elapsed = (now - pending.created_at).total_seconds()
                if elapsed > timeout_seconds:
                    expired_ids.append(request_id)

            for request_id in expired_ids:
                pending = self._pending.pop(request_id)
                if not pending.response_future.done():
                    pending.response_future.cancel()

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired requests")

        return len(expired_ids)

    def get_pending_count(self) -> int:
        """获取待处理请求数量"""
        return len(self._pending)

    def get_queue_size(self) -> int:
        """获取消息队列大小"""
        return self._request_queue.qsize()

    async def close(self):
        """关闭管理器，取消所有待处理请求"""
        async with self._lock:
            for request_id, pending in self._pending.items():
                if not pending.response_future.done():
                    pending.response_future.cancel()
            self._pending.clear()

        # 清空队列
        while not self._request_queue.empty():
            try:
                self._request_queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# Convenience functions for global instance

async def request_user_input(
    message: str,
    schema: Dict[str, Any],
    timeout_seconds: float = 60.0
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """请求用户输入的便捷函数"""
    manager = await ActionRequiredManager.get_instance()
    return await manager.request_and_wait(message, schema, timeout_seconds)


async def request_tool_confirmation(
    tool_name: str,
    arguments: Dict[str, Any],
    prompt: Optional[str] = None,
    timeout_seconds: float = 60.0
) -> Tuple[bool, Optional[bool]]:
    """请求工具确认的便捷函数"""
    manager = await ActionRequiredManager.get_instance()
    return await manager.request_tool_confirmation(
        tool_name, arguments, prompt, timeout_seconds
    )


async def submit_user_response(
    request_id: str,
    user_data: Dict[str, Any]
) -> bool:
    """提交用户响应的便捷函数"""
    manager = await ActionRequiredManager.get_instance()
    return await manager.submit_response(request_id, user_data)
