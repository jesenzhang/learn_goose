"""
远端数据库管理器 - 支持通过接口操作远端数据库

符合 DatabaseProtocol 协议
支持多用户数据隔离
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import httpx

from .protocol import DatabaseProtocol, MemoryProtocol

logger = logging.getLogger(__name__)


class RemoteDatabaseManager:
    """远端数据库管理器 - 通过 HTTP API 操作远端数据库"""

    def __init__(
        self,
        api_base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30
    ):
        """
        初始化远端数据库管理器

        Args:
            api_base_url: 远端数据库 API 基础地址
            api_key: API 密钥（可选）
            timeout: 请求超时时间（秒）
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self._session: Optional[httpx.AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """
        初始化远端数据库连接

        检查远端服务是否可用
        """
        if self._initialized:
            return

        # 通过健康检查验证连接
        is_healthy = await self.health_check()
        if not is_healthy:
            logger.warning(f"Remote database at {self.api_base_url} health check failed, but continuing anyway")

        self._initialized = True
        logger.info(f"Remote database connection initialized: {self.api_base_url}")

    async def _get_session(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端会话"""
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._get_headers()
            )
        return self._session

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行 HTTP 请求"""
        url = f"{self.api_base_url}/{endpoint.lstrip('/')}"
        try:
            session = await self._get_session()
            response = await session.request(
                method=method,
                url=url,
                json=data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request Error: {e}")
            raise

    async def save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """保存会话状态到远端数据库"""
        try:
            data = {
                "session_id": session_id,
                "state": state,
                "updated_at": datetime.now().isoformat()
            }
            await self._request("POST", "/states", data=data)
            logger.debug(f"Saved state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从远端数据库加载会话状态"""
        try:
            result = await self._request("GET", f"/states/{session_id}")
            return result.get("state")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    async def delete_state(self, session_id: str) -> bool:
        """删除会话状态"""
        try:
            await self._request("DELETE", f"/states/{session_id}")
            logger.debug(f"Deleted state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete state: {e}")
            return False

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            会话信息列表
        """
        try:
            result = await self._request("GET", "/sessions")
            sessions = result.get("sessions", [])
            # 兼容两种格式：直接返回 dict 列表，或者返回需要转换的数据
            if sessions and isinstance(sessions, list):
                # 如果返回的是字符串列表，需要转换为字典格式
                if sessions and isinstance(sessions[0], str):
                    return [{"id": s, "title": "Remote Session", "updated_at": 0} for s in sessions]
                return sessions
            return []
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    async def save_event(self, session_id: str, event: Dict[str, Any]) -> bool:
        """保存事件到远端数据库"""
        try:
            data = {
                "session_id": session_id,
                "event": event,
                "timestamp": datetime.now().isoformat()
            }
            await self._request("POST", "/events", data=data)
            logger.debug(f"Saved event for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save event: {e}")
            return False

    async def load_events(
        self,
        session_id: str,
        limit: Optional[int] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从远端数据库加载事件

        Args:
            session_id: 会话 ID
            limit: 返回数量限制
            since: 起始时间（ISO 格式）

        Returns:
            事件列表
        """
        try:
            params = {}
            if limit:
                params["limit"] = limit
            if since:
                params["since"] = since
            result = await self._request("GET", f"/events/{session_id}", params=params)
            return result.get("events", [])
        except Exception as e:
            logger.error(f"Failed to load events: {e}")
            return []

    async def delete_events(self, session_id: str, before: Optional[str] = None) -> int:
        """
        删除事件

        Args:
            session_id: 会话 ID
            before: 删除此时间之前的事件（ISO 格式）

        Returns:
            删除的事件数量
        """
        try:
            data = {"session_id": session_id}
            if before:
                data["before"] = before
            result = await self._request("DELETE", f"/events/{session_id}", data=data)
            return result.get("deleted_count", 0)
        except Exception as e:
            logger.error(f"Failed to delete events: {e}")
            return 0

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._request("GET", "/health")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息

        Returns:
            统计信息字典
        """
        try:
            result = await self._request("GET", "/stats")
            return result
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    async def close(self) -> None:
        """关闭 HTTP 客户端连接"""
        if self._session:
            await self._session.aclose()
            self._session = None
            logger.debug("Remote database connection closed")

    # ================= Multi-User Support Methods =================

    async def save_state_for_user(
        self,
        user_id: str,
        session_id: str,
        state: Dict[str, Any]
    ) -> bool:
        """
        为指定用户保存会话状态到远端数据库

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            state: 状态数据

        Returns:
            是否保存成功
        """
        try:
            # 在 state 中添加 user_id
            state['user_id'] = user_id

            data = {
                "session_id": session_id,
                "user_id": user_id,
                "state": state,
                "updated_at": datetime.now().isoformat()
            }
            await self._request("POST", "/states", data=data)
            logger.debug(f"Saved state for user {user_id}, session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save state for user {user_id}: {e}")
            return False

    async def load_state_for_user(
        self,
        user_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        从远端数据库加载指定用户的会话状态

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            状态数据，如果不存在则返回 None
        """
        try:
            # 使用查询参数传递 user_id
            result = await self._request(
                "GET",
                f"/states/{session_id}",
                params={"user_id": user_id}
            )
            return result.get("state")
        except Exception as e:
            logger.error(f"Failed to load state for user {user_id}: {e}")
            return None

    async def list_sessions_for_user(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        列出指定用户的会话

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            会话列表
        """
        try:
            params = {"user_id": user_id}
            if limit:
                params["limit"] = limit

            result = await self._request("GET", "/sessions", params=params)
            sessions = result.get("sessions", [])

            # 确保返回的会话包含 user_id
            for session in sessions:
                if 'user_id' not in session:
                    session['user_id'] = user_id

            return sessions
        except Exception as e:
            logger.error(f"Failed to list sessions for user {user_id}: {e}")
            return []

    async def delete_user_sessions(self, user_id: str) -> int:
        """
        删除指定用户的所有会话

        Args:
            user_id: 用户 ID

        Returns:
            删除的会话数量
        """
        try:
            result = await self._request(
                "DELETE",
                f"/users/{user_id}/sessions"
            )
            return result.get("deleted_sessions", 0)
        except Exception as e:
            logger.error(f"Failed to delete sessions for user {user_id}: {e}")
            return 0

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户统计信息

        Args:
            user_id: 用户 ID

        Returns:
            用户统计信息
        """
        try:
            result = await self._request("GET", f"/users/{user_id}/stats")
            return result
        except Exception as e:
            logger.error(f"Failed to get stats for user {user_id}: {e}")
            return {
                "user_id": user_id,
                "sessions": 0,
                "events": 0,
                "memories": 0
            }

    async def list_all_users(self) -> List[Dict[str, Any]]:
        """
        列出所有用户

        Returns:
            用户列表
        """
        try:
            result = await self._request("GET", "/users")
            return result.get("users", [])
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

    # ================= Memory Operations =================

    async def add_memory(self, user_id: str, content: str) -> bool:
        """
        添加记忆到远端数据库

        Args:
            user_id: 用户 ID
            content: 记忆内容

        Returns:
            是否添加成功
        """
        try:
            data = {
                "user_id": user_id,
                "content": content
            }
            await self._request("POST", "/memories", data=data)
            logger.debug(f"Added memory for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return False

    async def get_memories(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        从远端数据库获取记忆

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        try:
            params = {"user_id": user_id, "limit": limit}
            result = await self._request("GET", "/memories", params=params)
            return result.get("memories", [])
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return []

    async def search_memories(self, user_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索记忆

        Args:
            user_id: 用户 ID
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        try:
            params = {"user_id": user_id, "query": query, "limit": limit}
            result = await self._request("GET", "/memories/search", params=params)
            return result.get("memories", [])
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    async def delete_memory(self, memory_id: int) -> bool:
        """
        删除记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            是否删除成功
        """
        try:
            await self._request("DELETE", f"/memories/{memory_id}")
            logger.debug(f"Deleted memory {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
