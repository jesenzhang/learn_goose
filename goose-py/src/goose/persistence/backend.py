from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional, Tuple

class StorageBackend(ABC):
    """
    持久化层抽象基类。
    任何数据库驱动（SQLite, PostgreSQL, MySQL）都必须实现这些方法。
    """

    @abstractmethod
    async def connect(self):
        """建立数据库连接池"""
        pass

    @abstractmethod
    async def close(self):
        """关闭数据库连接"""
        pass

    @abstractmethod
    async def execute(self, query: str, params: tuple = ()) -> None:
        """执行写操作 (INSERT, UPDATE, DELETE)"""
        pass

    @abstractmethod
    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """查询单条记录，返回字典"""
        pass

    @abstractmethod
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """查询多条记录，返回字典列表"""
        pass

    @abstractmethod
    async def execute_script(self, script: str) -> None:
        """执行原始 SQL 脚本 (用于批量建表)"""
        pass