from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional, AsyncGenerator
from contextlib import asynccontextmanager


class StorageBackend(ABC):
    """
    持久化层抽象基类。
    适配 SQLAlchemy Core 风格，屏蔽 SQLite/PostgreSQL/MySQL 差异。
    """

    @abstractmethod
    async def connect(self):
        """建立数据库连接池"""
        pass

    @abstractmethod
    async def close(self):
        """关闭数据库连接池"""
        pass

    @abstractmethod
    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        执行写操作 (INSERT, UPDATE, DELETE)。
        :return: 建议返回 CursorResult 或受影响的行数，以便获取 last_insert_id
        """
        pass

    @abstractmethod
    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行读操作，返回字典列表"""
        pass

    @abstractmethod
    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """执行读操作，返回单行字典"""
        pass

    @abstractmethod
    async def execute_script(self, script: str) -> None:
        """执行原始 SQL 脚本 (主要用于 Schema 初始化)"""
        pass

    # [关键改进] 使用 @asynccontextmanager 实现 Pythonic 的事务管理
    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """
        事务上下文管理器。
        用法:
            async with backend.transaction():
                await backend.execute(...)
                await backend.execute(...)
        """
        yield
        

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncGenerator
from contextlib import asynccontextmanager
from .spec import TableSpec

class PersistenceBackend(ABC):
    """
    [Interface] 统一持久化后端接口 (支持 Batch & Filter)
    """
    @abstractmethod
    async def boot(self, schemas: List[Dict]): pass

    # --- 基础 CRUD ---
    @abstractmethod
    async def insert(self, spec: TableSpec, data: Dict[str, Any]): pass

    @abstractmethod
    async def get(self, spec: TableSpec, pk_value: Any) -> Optional[Dict]: pass

    @abstractmethod
    async def update(self, spec: TableSpec, pk_value: Any, data: Dict[str, Any]): pass

    @abstractmethod
    async def upsert(self, spec: TableSpec, data: Dict[str, Any]): pass

    @abstractmethod
    async def delete(self, spec: TableSpec, pk_value: Any): pass

    # --- 高级/批量查询 ---
    @abstractmethod
    async def get_batch(self, spec: TableSpec, pk_values: List[Any]) -> List[Dict]:
        """批量根据主键获取"""
        pass

    @abstractmethod
    async def find(self, spec: TableSpec, filters: Dict[str, Any], limit: int=-1, offset: int=0) -> List[Dict]:
        """根据条件精确筛选 (AND关系)"""
        pass

    @abstractmethod
    async def count(self, spec: TableSpec, filters: Dict[str, Any]) -> int:
        pass

    # --- 批量写 ---
    @abstractmethod
    async def update_by(self, spec: TableSpec, filters: Dict[str, Any], data: Dict[str, Any]) -> int:
        """根据条件批量更新"""
        pass

    @abstractmethod
    async def delete_by(self, spec: TableSpec, filters: Dict[str, Any]) -> int:
        """根据条件批量删除"""
        pass

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        yield