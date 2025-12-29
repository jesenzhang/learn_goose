import logging
from typing import List, Optional, Dict, Any
from .backend import StorageBackend

logger = logging.getLogger("goose.persistence.manager")

class PersistenceManager:
    """
    持久化层管理器 (Singleton)。
    负责管理 Backend 实例，并统一执行各模块注册的建表语句。
    """
    _instance = None

    def __init__(self, backend: StorageBackend):
        self.backend = backend
        self._schemas: List[str] = []
        self._initialized = False

    @classmethod
    def initialize(cls, backend: StorageBackend) -> "PersistenceManager":
        """初始化全局单例"""
        cls._instance = cls(backend)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "PersistenceManager":
        if not cls._instance:
            raise RuntimeError("PersistenceManager not initialized. Call initialize() first.")
        return cls._instance

    def register_schema(self, sql: str):
        """
        供各模块调用，注册自己的建表语句。
        """
        self._schemas.append(sql)

    async def execute(self, query: str, params: tuple = ()) -> None:
        """执行写操作 (INSERT, UPDATE, DELETE)"""
        # 直接透传给 backend.execute
        return await self.backend.execute(query, params)
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行查询操作 (SELECT)，返回列表"""
        # 直接透传给 backend.fetch_all
        return await self.backend.fetch_all(query, params)

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """执行查询操作 (SELECT)，返回单行"""
        # 直接透传给 backend.fetch_one
        return await self.backend.fetch_one(query, params)
     
    async def boot(self):
        """
        系统启动时调用。连接数据库并创建所有表。
        """
        if self._initialized:
            return

        logger.info("🚀 Booting Persistence Layer...")
        await self.backend.connect()
        
        # 统一执行所有注册的 Schema
        for sql in self._schemas:
            try:
                await self.backend.execute(sql)
            except Exception as e:
                # 容错：即使某个表创建失败（例如已存在），也不阻断
                logger.warning(f"Schema execution warning: {e}")
        
        self._initialized = True
        logger.info("✅ Persistence Layer Ready.")

    async def shutdown(self):
        await self.backend.close()