from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from contextlib import asynccontextmanager
from .spec import TableSpec

class PersistenceBackend(ABC):
    """
    [Interface] 统一持久化后端接口 (支持 Batch & Filter)
    """
    @abstractmethod
    async def boot(self, schemas: List[Union[str, List[str]]]): pass

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
    async def close(self):
        """关闭后端连接"""
        pass

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        yield
