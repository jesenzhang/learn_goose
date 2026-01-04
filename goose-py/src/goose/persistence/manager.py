import logging
import asyncio
from typing import List, Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

# 引入新的接口定义
from .backend import StorageBackend

logger = logging.getLogger("goose.persistence.manager")

class PersistenceManager:
    """
    持久化层管理器 (Singleton / Facade)。
    作为系统与具体 Backend 之间的代理，负责生命周期管理和 Schema 注册。
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.backend: Optional[StorageBackend] = None
        self._schemas: List[str] = []
        self._is_booted = False
        self._initialized = True
        logger.debug("📦 PersistenceManager initialized.")

    def set_backend(self, backend: StorageBackend):
        """注入后端实例"""
        self.backend = backend
        logger.info(f"🔌 Storage Backend set to: {type(backend).__name__}")

    def _check_ready(self):
        if not self.backend:
            raise RuntimeError("Persistence layer not ready. Backend is None.")

    # ==========================================
    # Schema 管理 (核心修复)
    # ==========================================

    def register_schema(self, script: str):
        """
        注册 Schema 脚本。
        改动：使用 execute_script 而不是 execute。
        """
        if script not in self._schemas:
            self._schemas.append(script)
            
            # 如果系统已启动，立即热更新
            if self._is_booted:
                logger.info("⚡ System booted. Executing new schema script immediately.")
                self._schedule_script_execution(script)

    def _schedule_script_execution(self, script: str):
        """辅助方法：在当前循环中调度脚本执行"""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._run_script_safe(script))
        except RuntimeError:
            pass

    async def _run_script_safe(self, script: str):
        """安全执行脚本"""
        self._check_ready()
        try:
            # [关键] 调用 execute_script，支持多条语句
            await self.backend.execute_script(script)
        except Exception as e:
            logger.warning(f"Schema execution warning: {e}")

    async def boot(self):
        """启动：连接数据库并应用所有 Schema"""
        if not self.backend:
            raise RuntimeError("❌ Cannot boot: No backend set.")
        
        logger.info("🚀 Booting Persistence Layer...")
        await self.backend.connect()
        self._is_booted = True
        
        # 应用所有注册的 Schema
        for script in self._schemas:
            await self._run_script_safe(script)
            
        logger.info("✅ Persistence Layer Ready.")

    async def shutdown(self):
        if self.backend:
            await self.backend.close()
            logger.info("💤 Persistence Layer Shutdown.")

    # ==========================================
    # 数据操作代理 (Delegate)
    # ==========================================

    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """写操作代理"""
        self._check_ready()
        return await self.backend.execute(query, params)

    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """读操作代理 (列表)"""
        self._check_ready()
        return await self.backend.fetch_all(query, params)

    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """读操作代理 (单行)"""
        self._check_ready()
        return await self.backend.fetch_one(query, params)

    # ==========================================
    # 事务支持 (新增)
    # ==========================================

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """
        事务代理。
        用法:
            async with persistence_manager.transaction():
                await persistence_manager.execute(...)
        """
        self._check_ready()
        # 透传 Backend 的上下文管理器
        async with self.backend.transaction():
            yield


# 全局单例
persistence_manager = PersistenceManager()