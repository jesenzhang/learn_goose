from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncGenerator
from contextlib import asynccontextmanager

class SQLDriver(ABC):
    """
    [Adapter Interface] SQL 驱动适配器接口
    无论底层用 SQLAlchemy, databases 还是 raw aiosqlite，都必须适配成这个样子。
    """

    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """执行写操作"""
        pass

    @abstractmethod
    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """执行读操作 (单行)"""
        pass

    @abstractmethod
    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行读操作 (多行)"""
        pass

    @abstractmethod
    async def execute_script(self, script: str) -> None:
        """执行 DDL 脚本"""
        pass

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """事务上下文"""
        yield
