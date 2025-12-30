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
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """
        [魔法方法 1] 单例守卫
        确保内存中永远只有一个 PersistenceManager 实例。
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.backend: Optional[StorageBackend] = None
        self._schemas: List[str] = []
        
        self._initialized = True
        logger.debug("📦 PersistenceManager instance created (Singleton).")

    def set_backend(self, backend: StorageBackend):
        """注入后端存储 (可以在实例化之后调用)"""
        self.backend = backend
        logger.info(f"🔌 Storage Backend set to: {type(backend).__name__}")
    
    @classmethod
    def get_instance(cls) -> "PersistenceManager":
        """
        获取单例。
        为了兼容性保留，实际上直接使用模块级变量 persistence_manager 更好。
        """
        if cls._instance is None:
            # 自动创建，不再报错
            return cls()
        return cls._instance
    
    @classmethod
    def initialize(cls, backend: StorageBackend) -> "PersistenceManager":
        """初始化全局单例"""
        cls._instance.set_backend(backend)
        return cls._instance

    def register_schema(self, sql: str):
        """
        供各模块调用，注册自己的建表语句。
        """
        if sql not in self._schemas:
            self._schemas.append(sql)

    def _check_ready(self):
        if not self.backend:
            raise RuntimeError("Persistence layer not ready. Did you await persistence_manager.boot()?")
        
    async def execute(self, query: str, params: tuple = ()) -> None:
        """执行写操作 (INSERT, UPDATE, DELETE)"""
        self._check_ready()
        return await self.backend.execute(query, params)
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行查询操作 (SELECT)，返回列表"""
        self._check_ready()
        return await self.backend.fetch_all(query, params)

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """执行查询操作 (SELECT)，返回单行"""
        self._check_ready()
        return await self.backend.fetch_one(query, params)
     
    async def boot(self):
        """
        系统启动时调用。连接数据库并创建所有表。
        """
        if not self.backend:
            raise RuntimeError("❌ Cannot boot PersistenceManager: No backend set. Call set_backend() first.")
        
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
        if self.backend:
            await self.backend.close()
            logger.info("💤 Persistence Layer Shutdown.")


persistence_manager = PersistenceManager()