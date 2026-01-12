import logging
from typing import Optional

# 导入接口和实现
from .backend import PersistenceBackend
from .backends.jsonl_backend import JsonlBackend
from .backends.sql_backend import SQLBackend
from .backends.http_backend import HTTPBackend, parse_db_url
from .repository import BaseRepository

logger = logging.getLogger("goose.persistence")

class PersistenceManager:
    """
    [Factory & Coordinator] 持久化层管理器

    职责：
    1. 解析 db_url，实例化对应的 Backend (SQL、JSONL 或 HTTP)。
    2. 管理全局数据库连接的生命周期 (Boot/Shutdown)。
    3. 协调 Schema 的自动注册与初始化。
    """

    def __init__(self, db_url: str = "file://./data"):
        """
        :param db_url: 连接字符串
               - 开发环境: "file://./data" 或 "file:///abs/path/to/data"
               - 生产环境: "sqlite:///goose.db", "postgresql://user:pass@host/db"
               - HTTP API: "http://localhost:8000" 或 "https://api.example.com"
               - HTTP API with key: "http://localhost:8000?api_key=xxx"
               - HTTP API with config: "http://localhost:8000?api_key=xxx&timeout=60"
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

        # 1. HTTP API 后端
        if uri.startswith("http://") or uri.startswith("https://"):
            base_url, api_key, config_kwargs = parse_db_url(uri)
            logger.info(f"🌐 persistence: Using HTTP Backend (url={base_url})")
            return HTTPBackend(base_url=base_url, api_key=api_key, **config_kwargs)

        # 2. JSONL 文件后端
        elif uri.startswith("file://") or uri.endswith(".jsonl"):
            # 解析路径: file://./data -> ./data
            path = uri.replace("file://", "")
            if not path:
                path = "./data" # 默认值

            logger.info(f"📂 persistence: Using JSONL Backend (path={path})")
            return JsonlBackend(data_dir=path)

        # 3. SQL 数据库后端 (SQLite, Postgres, MySQL)
        # 只要包含 "://", 且不是 file://、http://、https://，我们都认为是数据库连接串
        elif "://" in uri:
            logger.info(f"🗄️ persistence: Using SQL Backend (url={uri})")
            return SQLBackend(db_url=uri)

        # 4. 未知协议 fallback
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

