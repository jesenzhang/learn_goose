"""
Database Protocol - 统一的数据库接口协议定义

定义本地和远端数据库都需要实现的异步接口
避免循环引用，保持基础设施层的独立性
"""

from typing import Protocol, Dict, Any, List, Optional, runtime_checkable


@runtime_checkable
class DatabaseProtocol(Protocol):
    """
    数据库接口协议 - 定义所有数据库实现必须遵循的契约

    所有方法都是异步的，确保在异步上下文中不会阻塞事件循环
    """

    async def save_state(self, session_id: int, state: Dict[str, Any]) -> bool:
        """
        保存会话状态

        Args:
            session_id: 会话 ID
            state: 状态数据（字典格式）

        Returns:
            是否保存成功
        """
        ...

    async def load_state(self, session_id: int) -> Optional[Dict[str, Any]]:
        """
        加载会话状态

        Args:
            session_id: 会话 ID

        Returns:
            状态数据字典，如果不存在则返回 None
        """
        ...

    async def delete_state(self, session_id: int) -> bool:
        """
        删除会话状态

        Args:
            session_id: 会话 ID

        Returns:
            是否删除成功
        """
        ...

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            会话信息列表
        """
        ...

    async def save_event(self, session_id: int, event: Dict[str, Any]) -> bool:
        """
        保存事件

        Args:
            session_id: 会话 ID
            event: 事件数据（字典格式）

        Returns:
            是否保存成功
        """
        ...

    async def load_events(
        self,
        session_id: int,
        limit: Optional[int] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        加载事件

        Args:
            session_id: 会话 ID
            limit: 返回数量限制
            since: 起始时间（ISO 格式）

        Returns:
            事件列表
        """
        ...

    async def delete_events(self, session_id: int, before: Optional[str] = None) -> int:
        """
        删除事件

        Args:
            session_id: 会话 ID
            before: 删除此时间之前的事件（ISO 格式）

        Returns:
            删除的事件数量
        """
        ...

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            数据库是否可用
        """
        ...

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息

        Returns:
            统计信息字典
        """
        ...

    async def close(self) -> None:
        """
        关闭数据库连接
        """
        ...


# ================= Multi-User Support Methods =================

@runtime_checkable
class MultiUserDatabaseProtocol(Protocol):
    """
    多用户数据库协议 - 扩展的数据库接口

    定义多用户数据隔离相关的方法
    所有方法都是可选的（实现可以不支持多用户）
    """

    async def save_state_for_user(
        self,
        user_id: int,
        session_id: int,
        state: Dict[str, Any]
    ) -> bool:
        """
        为指定用户保存会话状态

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            state: 状态数据

        Returns:
            是否保存成功
        """
        ...

    async def load_state_for_user(
        self,
        user_id: int,
        session_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        加载指定用户的会话状态

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            状态数据，如果不存在则返回 None
        """
        ...

    async def list_sessions_for_user(
        self,
        user_id: int,
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
        ...

    async def delete_user_sessions(self, user_id: int) -> int:
        """
        删除指定用户的所有会话

        Args:
            user_id: 用户 ID

        Returns:
            删除的会话数量
        """
        ...

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户统计信息

        Args:
            user_id: 用户 ID

        Returns:
            用户统计信息
        """
        ...

    async def list_all_users(self) -> List[Dict[str, Any]]:
        """
        列出所有用户

        Returns:
            用户列表
        """
        ...


# ================= Memory Operations (Optional) =================

@runtime_checkable
class MemoryProtocol(Protocol):
    """
    记忆操作协议 - 可选的记忆存储功能
    """

    async def add_memory(self, user_id: int, content: str) -> bool:
        """
        添加记忆

        Args:
            user_id: 用户/会话 ID
            content: 记忆内容

        Returns:
            是否添加成功
        """
        ...

    async def get_memories(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取记忆

        Args:
            user_id: 用户/会话 ID
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        ...

    async def search_memories(self, user_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索记忆

        Args:
            user_id: 用户/会话 ID
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        ...

    async def delete_memory(self, memory_id: int) -> bool:
        """
        删除记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            是否删除成功
        """
        ...


# ================= Type Ali =================

# 为了向后兼容，保留类型别名
DatabaseInterfaceProtocol = DatabaseProtocol

