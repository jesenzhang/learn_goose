# import logging
# import asyncio
# from typing import List, Optional, Dict, Any, AsyncGenerator
# from contextlib import asynccontextmanager

# # 引入新的接口定义
# from .backend import StorageBackend, PersistenceBackend
# from .repository import BaseRepository

# logger = logging.getLogger("goose.persistence.manager")

# class PersistenceManager:
#     """
#     持久化层管理器 (Singleton / Facade)。
#     作为系统与具体 Backend 之间的代理，负责生命周期管理和 Schema 注册。
#     """
#     _instance = None
#     _initialized = False

#     def __new__(cls, *args, **kwargs):
#         if cls._instance is None:
#             cls._instance = super().__new__(cls)
#         return cls._instance

#     def __init__(self):
#         if self._initialized:
#             return
#         self.backend: Optional[PersistenceBackend] = None
#         self._schemas: List[str] = []
#         self._is_booted = False
#         self._initialized = True
#         logger.debug("📦 PersistenceManager initialized.")

#     def set_backend(self, backend: PersistenceBackend):
#         """注入后端实例"""
#         self.backend = backend
#         logger.info(f"🔌 Storage Backend set to: {type(backend).__name__}")

#     def _check_ready(self):
#         if not self.backend:
#             raise RuntimeError("Persistence layer not ready. Backend is None.")

#     # ==========================================
#     # Schema 管理 (核心修复)
#     # ==========================================

#     def register_schema(self, script: str):
#         """
#         注册 Schema 脚本。
#         改动：使用 execute_script 而不是 execute。
#         """
#         if script not in self._schemas:
#             self._schemas.append(script)
            
#             # 如果系统已启动，立即热更新
#             if self._is_booted:
#                 logger.info("⚡ System booted. Executing new schema script immediately.")
#                 self._schedule_script_execution(script)

#     def _schedule_script_execution(self, script: str):
#         """辅助方法：在当前循环中调度脚本执行"""
#         try:
#             loop = asyncio.get_running_loop()
#             if loop.is_running():
#                 loop.create_task(self._run_script_safe(script))
#         except RuntimeError:
#             pass

#     async def _run_script_safe(self, script: str):
#         """安全执行脚本"""
#         self._check_ready()
#         try:
#             # [关键] 调用 execute_script，支持多条语句
#             await self.backend.execute_script(script)
#         except Exception as e:
#             logger.warning(f"Schema execution warning: {e}")

#     async def boot(self):
#         """启动：连接数据库并应用所有 Schema"""
        
#         print(f"🏭 Manager Boot BaseRepo ID: {id(BaseRepository)}") # 打印内存地址
        
#         if not self.backend:
#             raise RuntimeError("❌ Cannot boot: No backend set.")
        
#         logger.info("🚀 Booting Persistence Layer...")
#         await self.backend.connect()
#         self._is_booted = True
        
#         schemas = BaseRepository.get_all_schemas()
#         if schemas:
#             logger.info(f"🔨 Applying {len(schemas)} registered schemas...")
#             for sql in schemas:
#                 try:
#                     # 假设 execute 是执行 SQL 的方法
#                     await self._run_script_safe(sql)
#                 except Exception as e:
#                     logger.error(f"Failed to apply schema:\n{sql}\nError: {e}")
#                     raise e
                
#         # 应用所有注册的 Schema
#         for script in self._schemas:
#             await self._run_script_safe(script)
            
#         logger.info("✅ Persistence Layer Ready.")

#     async def shutdown(self):
#         if self.backend:
#             await self.backend.close()
#             logger.info("💤 Persistence Layer Shutdown.")

#     # ==========================================
#     # 数据操作代理 (Delegate)
#     # ==========================================

#     async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
#         """写操作代理"""
#         self._check_ready()
#         return await self.backend.execute(query, params)

#     async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
#         """读操作代理 (列表)"""
#         self._check_ready()
#         return await self.backend.fetch_all(query, params)

#     async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
#         """读操作代理 (单行)"""
#         self._check_ready()
#         return await self.backend.fetch_one(query, params)

#     # ==========================================
#     # 事务支持 (新增)
#     # ==========================================

#     @asynccontextmanager
#     async def transaction(self) -> AsyncGenerator[None, None]:
#         """
#         事务代理。
#         用法:
#             async with persistence_manager.transaction():
#                 await persistence_manager.execute(...)
#         """
#         self._check_ready()
#         # 透传 Backend 的上下文管理器
#         async with self.backend.transaction():
#             yield

import logging
import asyncio
from typing import Optional

# 导入接口和实现
from .backend import PersistenceBackend
from .backends.jsonl_backend import JsonlBackend
from .backends.sql_backend import SQLBackend
from .repository import BaseRepository

logger = logging.getLogger("goose.persistence")

class PersistenceManager:
    """
    [Factory & Coordinator] 持久化层管理器
    
    职责：
    1. 解析 db_url，实例化对应的 Backend (SQL 或 JSONL)。
    2. 管理全局数据库连接的生命周期 (Boot/Shutdown)。
    3. 协调 Schema 的自动注册与初始化。
    """

    def __init__(self, db_url: str = "file://./data"):
        """
        :param db_url: 连接字符串
               - 开发环境: "file://./data" 或 "file:///abs/path/to/data"
               - 生产环境: "sqlite:///goose.db", "postgresql://user:pass@host/db"
        """
        self.db_url = db_url
        self._backend: Optional[PersistenceBackend] = None

    @property
    def backend(self) -> PersistenceBackend:
        """
        延迟加载 (Lazy Loading) 获取后端实例
        """
        if self._backend is None:
            self._backend = self._create_backend()
        return self._backend

    def _create_backend(self) -> PersistenceBackend:
        """根据 URL Scheme 决定使用哪个后端适配器"""
        uri = self.db_url
        
        # 1. JSONL 文件后端
        if uri.startswith("file://") or uri.endswith(".jsonl"):
            # 解析路径: file://./data -> ./data
            path = uri.replace("file://", "")
            if not path: 
                path = "./data" # 默认值
            
            logger.info(f"📂 persistence: Using JSONL Backend (path={path})")
            return JsonlBackend(data_dir=path)
        
        # 2. SQL 数据库后端 (SQLite, Postgres, MySQL)
        # 只要包含 "://", 且不是 file://，我们都认为是数据库连接串
        elif "://" in uri:
            logger.info(f"🗄️ persistence: Using SQL Backend (url={uri})")
            return SQLBackend(db_url=uri)
            
        # 3. 未知协议 fallback
        else:
            logger.warning(f"❓ persistence: Unknown scheme in '{uri}', falling back to JSONL.")
            return JsonlBackend(data_dir="./data")

    async def boot(self):
        """
        [System Start] 启动持久化层
        1. 建立数据库连接 (如果需要)
        2. 收集所有 Repository 定义的 TableSpec
        3. 执行建表语句 (SQL) 或 创建目录 (JSONL)
        """
        logger.info("🚀 persistence: Booting...")
        
        # 1. 收集 Schema (来自 BaseRepository 的自动注册机制)
        # 注意：此时所有 Repository 类必须已经被 import 过了
        schemas = BaseRepository.get_all_schemas()
        
        if not schemas:
            logger.warning("⚠️ persistence: No schemas found. Did you import your repositories?")
        
        # 2. 委托后端进行初始化
        try:
            await self.backend.boot(schemas)
            logger.info(f"✅ persistence: Booted successfully with {len(schemas)} tables.")
        except Exception as e:
            logger.critical(f"❌ persistence: Boot failed: {e}")
            raise e

    async def shutdown(self):
        """
        [System Stop] 关闭持久化层
        释放连接池、关闭文件句柄等
        """
        if self._backend:
            # 如果 Backend 实现了 close 方法（SQLBackend 有，JsonlBackend 可能没有）
            if hasattr(self._backend, 'close'):
                await self._backend.close() # type: ignore
            elif hasattr(self._backend, 'driver') and hasattr(self._backend.driver, 'close'):
                await self._backend.driver.close() # type: ignore
                
            logger.info("🛑 persistence: Shutdown complete.")

    def transaction(self):
        """
        快捷方式：直接获取后端的事务上下文
        async with pm.transaction(): ...
        """
        return self.backend.transaction()
    
    
# ==========================================
# 单例管理逻辑 (Global Instance Management)
# ==========================================

# 1. 定义一个模块级的全局变量
_GLOBAL_PM: Optional[PersistenceManager] = None

def init_persistence(db_url: str) -> PersistenceManager:
    """
    [System Startup] 全局初始化函数
    只应在 main.py 或 system.py 启动时调用一次
    """
    global _GLOBAL_PM
    if _GLOBAL_PM is not None:
        logger.warning("PersistenceManager is already initialized!")
        return _GLOBAL_PM
        
    logger.info(f"⚙️ Initializing Global PersistenceManager with {db_url}")
    _GLOBAL_PM = PersistenceManager(db_url)
    return _GLOBAL_PM

def get_persistence() -> PersistenceManager:
    """
    [Access Point] 获取全局单例
    供 Repository 或 Service 层调用
    """
    if _GLOBAL_PM is None:
        raise RuntimeError(
            "PersistenceManager has not been initialized. "
            "Please call 'init_persistence(db_url)' in your startup code."
        )
    return _GLOBAL_PM

async def shutdown_persistence():
    """全局关闭辅助函数"""
    global _GLOBAL_PM
    if _GLOBAL_PM:
        await _GLOBAL_PM.shutdown()
        _GLOBAL_PM = None

