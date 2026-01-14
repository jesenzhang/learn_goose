"""
统一的数据库接口 - 支持本地和远端数据库

使用 DatabaseProtocol 协议确保接口一致性
完全异步实现，不阻塞事件循环
支持多用户数据隔离
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List

from .protocol import DatabaseProtocol, MemoryProtocol, MultiUserDatabaseProtocol
from .async_manager import AsyncDatabaseManager
from .remote_db import RemoteDatabaseManager

logger = logging.getLogger(__name__)


class UnifiedDatabase:
    """
    统一数据库接口 - 自动选择本地或远端数据库

    符合 DatabaseProtocol 协议，提供统一的异步接口
    """

    def __init__(
        self,
        local_db_path: Optional[str] = None,
        remote_db_url: Optional[str] = None,
        remote_db_api_key: Optional[str] = None,
        use_remote: bool = False,
        timeout: int = 30
    ):
        """
        初始化统一数据库接口

        Args:
            local_db_path: 本地数据库路径
            remote_db_url: 远端数据库 URL
            remote_db_api_key: 远端数据库 API 密钥
            use_remote: 是否使用远端数据库
            timeout: HTTP 请求超时时间（仅用于远端数据库）
        """
        self.use_remote = use_remote
        self._local_db: Optional[AsyncDatabaseManager] = None
        self._remote_db: Optional[RemoteDatabaseManager] = None
        self._timeout = timeout

        # 预配置但不初始化（延迟初始化）
        if use_remote and remote_db_url:
            self._remote_db = RemoteDatabaseManager(
                api_base_url=remote_db_url,
                api_key=remote_db_api_key,
                timeout=timeout
            )
            logger.info(f"Configured remote database: {remote_db_url}")
        else:
            self._local_db = AsyncDatabaseManager(
                db_path=local_db_path or "agent_ultra.db"
            )
            logger.info(f"Configured local database: {local_db_path or 'agent_ultra.db'}")

    async def initialize(self):
        """
        初始化数据库连接

        需要在使用任何数据库操作之前调用
        """
        if self._remote_db:
            await self._remote_db.initialize()
        elif self._local_db:
            await self._local_db.initialize()

    # ================= DatabaseProtocol Implementation =================
    async def add_message(self, session_id: int, role: str, content: str, metadata: Dict = None, **kwargs) -> bool:
        """
        [Protocol] 添加消息
        API: POST /agent/handle/add_message
        Body: {session_id, role, content, Metadata: str(json)}
        """
        if self._remote_db:
            return await self._remote_db.add_message(session_id, role, content, metadata, **kwargs)
        elif self._local_db:
            return await self._local_db.add_message(session_id, role, content, metadata, **kwargs)
        return False
        
    async def save_state(self, session_id: int, state: Dict[str, Any]) -> bool:
        """保存会话状态"""
        if self._remote_db:
            return await self._remote_db.save_state(session_id, state)
        elif self._local_db:
            return await self._local_db.save_state(session_id, state)
        return False

    async def load_state(self, session_id: int) -> Optional[Dict[str, Any]]:
        """加载会话状态"""
        if self._remote_db:
            return await self._remote_db.load_state(session_id)
        elif self._local_db:
            return await self._local_db.load_state(session_id)
        return None

    async def delete_state(self, session_id: int) -> bool:
        """删除会话状态"""
        if self._remote_db:
            return await self._remote_db.delete_state(session_id)
        elif self._local_db:
            return await self._local_db.delete_state(session_id)
        return False

    async def list_sessions(self):
        """列出所有会话"""
        if self._remote_db:
            return await self._remote_db.list_sessions()
        elif self._local_db:
            return await self._local_db.list_sessions()
        return []

    async def save_event(self, session_id: int, event: Dict[str, Any]) -> bool:
        """保存事件"""
        if self._remote_db:
            return await self._remote_db.save_event(session_id, event)
        elif self._local_db:
            return await self._local_db.save_event(session_id, event)
        return False

    async def load_events(
        self,
        session_id: int,
        limit: Optional[int] = None,
        since: Optional[str] = None
    ):
        """加载事件"""
        if self._remote_db:
            return await self._remote_db.load_events(session_id, limit, since)
        elif self._local_db:
            return await self._local_db.load_events(session_id, limit, since)
        return []

    async def delete_events(self, session_id: int, before: Optional[str] = None) -> int:
        """删除事件"""
        if self._remote_db:
            return await self._remote_db.delete_events(session_id, before)
        elif self._local_db:
            return await self._local_db.delete_events(session_id, before)
        return 0

    async def health_check(self) -> bool:
        """健康检查"""
        if self._remote_db:
            return await self._remote_db.health_check()
        elif self._local_db:
            return await self._local_db.health_check()
        return False

    async def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        if self._remote_db:
            return await self._remote_db.get_stats()
        elif self._local_db:
            return await self._local_db.get_stats()
        return {}

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._remote_db:
            await self._remote_db.close()
        elif self._local_db:
            await self._local_db.close()

    # ================= Multi-User Methods =================

    async def save_state_for_user(self, user_id: int, session_id: int, state: Dict[str, Any]) -> bool:
        """为指定用户保存会话状态"""
        if self._remote_db and hasattr(self._remote_db, 'save_state_for_user'):
            return await self._remote_db.save_state_for_user(user_id, session_id, state)
        elif self._local_db:
            return await self._local_db.save_state_for_user(user_id, session_id, state)
        return False

    async def load_state_for_user(self, user_id: int, session_id: int) -> Optional[Dict[str, Any]]:
        """加载指定用户的会话状态"""
        if self._remote_db and hasattr(self._remote_db, 'load_state_for_user'):
            return await self._remote_db.load_state_for_user(user_id, session_id)
        elif self._local_db:
            return await self._local_db.load_state_for_user(user_id, session_id)
        return None

    async def list_sessions_for_user(self, user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """列出指定用户的会话"""
        if self._remote_db and hasattr(self._remote_db, 'list_sessions_for_user'):
            return await self._remote_db.list_sessions_for_user(user_id, limit)
        elif self._local_db:
            return await self._local_db.list_sessions_for_user(user_id, limit)
        return []

    async def delete_user_sessions(self, user_id: int) -> int:
        """删除指定用户的所有会话"""
        if self._remote_db and hasattr(self._remote_db, 'delete_user_sessions'):
            return await self._remote_db.delete_user_sessions(user_id)
        elif self._local_db:
            return await self._local_db.delete_user_sessions(user_id)
        return 0

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """获取用户统计信息"""
        if self._remote_db and hasattr(self._remote_db, 'get_user_stats'):
            return await self._remote_db.get_user_stats(user_id)
        elif self._local_db:
            return await self._local_db.get_user_stats(user_id)
        return {}

    async def list_all_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        if self._remote_db and hasattr(self._remote_db, 'list_all_users'):
            return await self._remote_db.list_all_users()
        elif self._local_db:
            return await self._local_db.list_all_users()
        return []

    # ================= Memory Methods =================

    async def add_memory(self, user_id: int, content: str) -> bool:
        """添加记忆"""
        if self._remote_db and hasattr(self._remote_db, 'add_memory'):
            return await self._remote_db.add_memory(user_id, content)
        elif self._local_db:
            return await self._local_db.add_memory(user_id, content)
        return False

    async def get_memories(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """获取记忆"""
        if self._remote_db and hasattr(self._remote_db, 'get_memories'):
            return await self._remote_db.get_memories(user_id, limit)
        elif self._local_db:
            return await self._local_db.get_memories(user_id, limit)
        return []

    async def search_memories(self, user_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索记忆"""
        if self._remote_db and hasattr(self._remote_db, 'search_memories'):
            return await self._remote_db.search_memories(user_id, query, limit)
        elif self._local_db:
            return await self._local_db.search_memories(user_id, query, limit)
        return []

    async def delete_memory(self, memory_id: int) -> bool:
        """删除记忆"""
        if self._remote_db and hasattr(self._remote_db, 'delete_memory'):
            return await self._remote_db.delete_memory(memory_id)
        elif self._local_db:
            return await self._local_db.delete_memory(memory_id)
        return False

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


# 兼容性别名
DatabaseInterface = UnifiedDatabase


# ================= Global Instance Management =================

_global_db: Optional[UnifiedDatabase] = None


def get_db() -> UnifiedDatabase:
    """
    获取全局数据库实例

    必须先调用 configure_db() 配置数据库

    Returns:
        统一数据库接口实例

    Raises:
        RuntimeError: 如果数据库未配置
    """
    global _global_db
    if _global_db is None:
        raise RuntimeError(
            "Database not configured. "
            "Call configure_db() first."
        )
    return _global_db


async def get_db_async() -> UnifiedDatabase:
    """
    获取全局数据库实例（异步版本）

    自动初始化数据库连接

    Returns:
        统一数据库接口实例
    """
    db = get_db()
    await db.initialize()
    return db


def configure_db(
    local_db_path: Optional[str] = None,
    remote_db_url: Optional[str] = None,
    remote_db_api_key: Optional[str] = None,
    use_remote: bool = False,
    timeout: int = 30
) -> UnifiedDatabase:
    """
    配置全局数据库实例

    Args:
        local_db_path: 本地数据库路径
        remote_db_url: 远端数据库 URL
        remote_db_api_key: 远端数据库 API 密钥
        use_remote: 是否使用远端数据库
        timeout: HTTP 请求超时时间

    Returns:
        配置好的数据库实例（需要调用 initialize() 初始化）
    """
    global _global_db
    _global_db = UnifiedDatabase(
        local_db_path=local_db_path,
        remote_db_url=remote_db_url,
        remote_db_api_key=remote_db_api_key,
        use_remote=use_remote,
        timeout=timeout
    )
    logger.info("Database configured successfully")
    return _global_db


async def shutdown_db() -> None:
    """关闭全局数据库连接"""
    global _global_db
    if _global_db:
        await _global_db.close()
        _global_db = None
        logger.info("Database shutdown complete")


# ================= Backward Compatibility =================

# 保留同步版本的 DatabaseManager 用于向后兼容
from .manager import DatabaseManager

__all__ = [
    # Protocol
    "DatabaseProtocol",
    "MultiUserDatabaseProtocol",
    "MemoryProtocol",

    # Unified Interface
    "UnifiedDatabase",
    "DatabaseInterface",

    # Implementations
    "AsyncDatabaseManager",
    "DatabaseManager",  # 同步版本（向后兼容）
    "RemoteDatabaseManager",

    # Global Management
    "get_db",
    "get_db_async",
    "configure_db",
    "shutdown_db",
]
