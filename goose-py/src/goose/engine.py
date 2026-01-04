import asyncio
import logging
from typing import Optional

# Imports
from goose.config import SystemConfig
from goose.persistence.manager import persistence_manager
from goose.persistence.drivers import SQLAlchemyBackend

# Events
from goose.events.bus import MemoryEventBus
from goose.events.store import SQLEventStore, register_event_store_schema

# Resources
from goose.resources.store import SystemResourceStore, UserResourceStore,register_resource_schema
from goose.resources.types import ResourceKind
from goose.providers import LLMBuilder
from goose.resources.presets import get_system_presets

# Globals
import goose.globals as G

# Modules schemas
from goose.session import register_session_schemas,SessionRepository
from goose.workflow import register_workflow_schemas,WorkflowRepository

# [适配] 引入新的 Schema 定义
# 建议：为了避免循环引用，Schema 定义最好放在单独的 constants 文件或 persistence/schemas.py
# 这里假设我们暂时从 repositories 导入，或者你手动定义在这里
from goose.app.execution.repository import (
    EXECUTION_SCHEMA, 
    EXECUTION_INDEX
)
from goose.app.trigger.repository import (
    TRIGGER_SCHEMA
)
from goose.app.user.repository import (
    USER_SCHEMA, 
    USER_RESOURCE_SCHEMA,
    USER_RESOURCE_INDEX
)

logger = logging.getLogger("goose.system")

class GooseEngine:
    """
    Goose 系统引擎。
    负责基础设施 (DB, Bus) 和运行时 (Runtime) 的构建。
    """
    def __init__(self, config: SystemConfig = None):
        self.config = config or SystemConfig()
        self.runtime: Optional[G.Runtime] = None

    async def start(self) -> G.Runtime:
        """启动系统"""
        logger.info("⚡ Engine starting...")
        
        # ==========================================
        # 1. 初始化持久层 (Infrastructure)
        # ==========================================
        db_path = self.config.db_url
        if not db_path.startswith("sqlite") and "://" not in db_path:
             db_url = f"sqlite+aiosqlite:///{db_path}"
        else:
             db_url = db_path
             
        # 初始化 Backend (会自动创建文件夹)
        backend = SQLAlchemyBackend(db_url)
        persistence_manager.set_backend(backend)
        
        # [核心适配] 注册所有 Schema
        # 确保在 boot() 之前注册，这样表才会被创建
        self._register_all_schemas()
        
        # 启动数据库连接
        await persistence_manager.boot()
        
        # ==========================================
        # 2. 创建核心组件 (Core Components)
        # ==========================================
        bus = MemoryEventBus(buffer_size=self.config.event_bus_size, ttl=self.config.event_ttl)
        event_store = SQLEventStore(persistence_manager)
        
        sys_store = SystemResourceStore()
        usr_store = UserResourceStore(persistence_manager)

        # ==========================================
        # 3. 创建工厂与预设
        # ==========================================
        factory = G.StreamerFactory(bus, event_store)
        
        presets = get_system_presets(self.config)
        logger.info(f"📦 Registering {len(presets)} system resources...")
        for meta in presets:
            sys_store.register(meta)
        
        # ==========================================
        # 4. 构建 Runtime
        # ==========================================
        self.runtime = G.Runtime(
            config=self.config,
            bus=bus,
            persister=persistence_manager,
            event_store=event_store,
            streamer_factory=factory,
            sys_store=sys_store,
            usr_store=usr_store,
        )
        
        # 5. 注册构建器
        self.runtime.register_global_builder(ResourceKind.LLM, LLMBuilder())
        
        
        # 6. 设置全局单例
        # 这对于 Service 层 (ExecutionService) 获取 Runtime 至关重要
        G.set_global_runtime(self.runtime)
        
        logger.info("✅ Engine infrastructure ready.")
        return self.runtime

    def _register_all_schemas(self):
        """
        [Helper] 集中注册所有数据库表结构
        """
        pm = persistence_manager
        
        # 1. 基础模块
        register_session_schemas()
        register_workflow_schemas() # 这里面包含 workflows 表
        register_event_store_schema()
        register_resource_schema(pm)
        
        # 3. [适配] 注册 App 层业务表
        pm.register_schema(EXECUTION_SCHEMA)
        pm.register_schema(EXECUTION_INDEX)
        pm.register_schema(TRIGGER_SCHEMA)
        
        pm.register_schema(USER_SCHEMA)
        pm.register_schema(USER_RESOURCE_SCHEMA)
        pm.register_schema(USER_RESOURCE_INDEX)
        
        logger.debug("📝 All schemas registered.")

    async def stop(self):
        """停止系统"""
        logger.info("💤 Engine stopping...")
        if self.runtime and self.runtime.persister:
            try:
                await self.runtime.persister.shutdown()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        
        G._GLOBAL_RUNTIME = None
        self.runtime = None
        logger.info("🛑 Engine stopped.")

    async def __aenter__(self) -> G.Runtime:
        return await self.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()