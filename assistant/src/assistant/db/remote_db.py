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
import json

from .protocol import DatabaseProtocol, MemoryProtocol
from ..utils.ctx_vars import get_auth_token

logger = logging.getLogger(__name__)


class RemoteDatabaseManager:
    """远端数据库管理器 - 通过 HTTP API 操作远端数据库"""

    def __init__(
        self,
        api_base_url: str = 'http://192.168.11.11:9980/gzclabeldebugaapi',
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
                timeout=self.timeout
            )
        self._session.headers.update(self._get_headers())
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
        headers = {"Content-Type": "application/json"}
        
        # 获取 Token
        dynamic_token = get_auth_token()
        
        if dynamic_token:
            headers["Authorization"] = dynamic_token
        elif self.api_key:
            headers["Authorization"] = self.api_key
        print(dynamic_token)
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行 HTTP 请求"""
        url = f"{self.api_base_url}/{endpoint.lstrip('/')}"
        try:
            session = await self._get_session()
            response = await session.request(
                method=method,
                url=url,
                json=json,
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

        
    async def save_state(self, session_id: int, state: Dict, **kwargs) -> bool:
        """
        [Protocol] 保存会话状态
        API: POST /agent/handle/save_state
        Body: {session_id: int, state: str(json)}
        """
        try:
            # API 要求 state 字段是 JSON 字符串
            state_str = json.dumps(state, ensure_ascii=False)
            
            payload = {
                "session_id": session_id,
                "state": state_str
            }

            res = await self._request("POST", "/agent/handle/save_state", params={"p":"w"} ,json=payload)
            return res.get("code") == 200 or res.get("status") == 1
        except Exception as e:
            logger.error(f"save_state error: {e}")
            return False

    async def load_state(self, session_id: int) -> Optional[Dict]:
        """
        [Protocol] 加载会话状态
        API: GET /agent/handle/load_state?session_id=...
        """
        res = await self._request("GET", f"/agent/handle/load_state", params={"session_id":session_id,"p":"w"})

        if res.get("code") == 200 or res.get("status") == 1:
            data = res.get("data")
            # 容错：有些 API 会把 JSON 存成字符串返回
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    pass
            return data
        return None

    async def delete_state(self, session_id: int) -> bool:
        """删除会话状态"""
        try:
            await self._request("DELETE", f"/states/{session_id}")
            logger.debug(f"Deleted state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete state: {e}")
            return False
        
    async def create_session(self, title: str = "New Chat") -> Optional[int]:
        """
        [Protocol Extension] 为用户创建新会话
        API: POST /assistant/session/add
        """
        try:
            # 构造符合业务逻辑的 Payload
            payload = {
                "session_name": title
            }

            res = await self._request("POST", "/assistant/session/add", json=payload)

            # 解析多种可能的返回格式
            if res.get("code") == 200 or res.get("status") == 1:
                data = res.get("data")
                if isinstance(data, dict):
                    session_id = data.get("session_id") or data.get("id")
                    return int(session_id) if session_id is not None else None
                if isinstance(data, (str, int)):
                    return int(data)

            logger.warning(f"Create session failed: {res}")
            return None
        except Exception as e:
            logger.error(f"create_user_session error: {e}")
            return None

    async def list_sessions(self, limit: int = 20, **kwargs) -> List[Dict]:
        """
        [Protocol] 获取会话列表
        API: GET /assistant/session/list
        """
        # API 似乎不支持 limit 参数，只支持 p=w
        res = await self._request("GET", "/assistant/session/list")

        if res.get("code") == 200 or res.get("status") == 1:
            data = res.get("data", [])
            # 协议要求返回 List[Dict]，如果 API 返回其他格式需适配
            if isinstance(data, list):
                return data[:limit] # 手动在客户端做 limit
        return []

    async def save_event(self, session_id: int, event: Dict, **kwargs) -> bool:
        """
        [Protocol] 保存事件
        API: POST /agent/handle/save_event
        Body: {session_id, event: str(json)}
        """
        try:
            event_str = json.dumps(event, ensure_ascii=False)

            payload = {
                "session_id": session_id,
                "event": event_str
            }

            res = await self._request("POST", "/agent/handle/save_event", json=payload)
            return res.get("code") == 200 or res.get("status") == 1
        except Exception as e:
            logger.error(f"save_event error: {e}")
            return False

    async def load_events(
        self,
        session_id: int,
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

    async def delete_events(self, session_id: int, before: Optional[str] = None) -> int:
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
            result = await self._request("DELETE", f"/events/{session_id}", json=data)
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

    async def add_message(self, session_id: int, role: str, content: str, metadata: Dict = None, **kwargs) -> bool:
        """
        [Protocol] 添加消息
        API: POST /agent/handle/add_message
        Body: {session_id, role, content, Metadata: str(json)}
        """
        try:
            metadata_str = json.dumps(metadata or {}, ensure_ascii=False)

            payload = {
                "session_id": session_id,
                "role": role,
                "content": content,
                # 【关键适配】API 字段首字母大写
                "Metadata": metadata_str
            }

            res = await self._request("POST", "/agent/handle/add_message", json=payload)
            return res.get("code") == 200 or res.get("status") == 1
        except Exception as e:
            logger.error(f"add_message error: {e}")
            return False

    # ================= Multi-User Support Methods =================

    async def save_state_for_user(
        self,
        user_id: int,
        session_id: int,
        state: Dict[str, Any]
    ) -> bool:
        """
        [Protocol Extension] 为特定用户保存状态

        策略：
        1. 将 user_id 注入到 state 字典内部，确保状态数据包含归属权。
        2. 调用基础的 save_state 接口。
        """
        try:
            # 深拷贝以避免修改原始引用，或者直接注入
            state_to_save = state.copy()
            state_to_save['user_id'] = user_id

            # 复用基础的 save_state 逻辑
            return await self.save_state(session_id, state_to_save)
        except Exception as e:
            logger.error(f"save_state_for_user error (user={user_id}): {e}")
            return False

    async def load_state_for_user(
        self,
        user_id: int,
        session_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        [Protocol Extension] 加载特定用户的状态

        策略：
        1. 调用基础 load_state。
        2. (可选) 在客户端进行鉴权，检查返回的 state['user_id'] 是否匹配。
        """
        state = await self.load_state(session_id)

        if state:
            # 安全检查：防止越权访问（如果后端没有做隔离的话）
            stored_user_id = state.get("user_id")
            if stored_user_id and int(stored_user_id) != user_id:
                logger.warning(f"Access Denied: Session {session_id} belongs to {stored_user_id}, not {user_id}")
                return None

        return state

    async def list_sessions_for_user(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        [Protocol Extension] 获取指定用户的会话列表
        API: GET /assistant/session/list?user_id=...
        """
        # 假设 API 支持通过 user_id 过滤
        params = {"user_id": user_id}

        # 复用 _request，它会自动处理 p=w 和 base_url
        res = await self._request("GET", "/assistant/session/list", params=params)

        if res.get("code") == 200 or res.get("status") == 1:
            data = res.get("data", [])
            if isinstance(data, list):
                # 如果 API 返回所有数据，我们在客户端做一次过滤作为兜底
                filtered = [
                    s for s in data
                    if int(s.get("user_id", user_id)) == user_id # 如果返回数据没user_id则默认属于该用户
                ]
                return filtered[:limit]
        return []

   
    async def delete_user_sessions(self, user_id: int) -> int:
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

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
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

    async def add_memory(self, user_id: int, content: str) -> bool:
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
            await self._request("POST", "/memories", json=data)
            logger.debug(f"Added memory for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return False

    async def get_memories(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
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

    async def search_memories(self, user_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
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
