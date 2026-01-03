import asyncio
import logging
from typing import Optional

# Imports
from goose.config import SystemConfig
from goose.persistence.manager import persistence_manager
from goose.persistence.drivers import SQLiteBackend
# Events
from goose.events.bus import MemoryEventBus
from goose.events.store import SQLEventStore
# Resources
from goose.resources.store import SystemResourceStore, UserResourceStore
from goose.resources.types import ResourceKind
from goose.providers import LLMBuilder
# Globals
import goose.globals as G
# Modules schemas
from goose.session import register_session_schemas
from goose.workflow import register_workflow_schemas
from goose.resources.presets import get_system_presets
from goose.events import register_event_store_schema # 假设你已经按照之前的建议分离了 schema 注册

logger = logging.getLogger("goose.system")

class GooseEngine:
    """
    Goose 系统引擎。
    负责整个系统的生命周期管理、依赖注入和运行时构建。
    """
    def __init__(self, config: SystemConfig = None):
        self.config = config or SystemConfig()
        self.runtime: Optional[G.Runtime] = None

    async def start(self) -> G.Runtime:
        """启动系统 (原 boot 逻辑)"""
        logger.info("⚡ Engine starting...")
        
        # 1. 初始化持久层
        backend = SQLiteBackend(self.config.db_url)
        persistence_manager.set_backend(backend)
        
        # 注册 Schema
        register_session_schemas()
        register_workflow_schemas()
        register_event_store_schema()
        
        await persistence_manager.boot()
        
        # 2. 创建核心组件
        bus = MemoryEventBus(buffer_size=self.config.event_bus_size, ttl=self.config.event_ttl)
        event_store = SQLEventStore(persistence_manager)
        
        sys_store = SystemResourceStore()
        usr_store = UserResourceStore(persistence_manager)

        # 3. 创建 Streamer 工厂
        factory = G.StreamerFactory(bus, event_store)
        
        # 注册预设资源
        presets = get_system_presets(self.config)
        logger.info(f"📦 Registering {len(presets)} system resources...")
        for meta in presets:
            sys_store.register(meta)
        
        # 4. 构建 Runtime
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
        
        # 6. [兼容性] 设置全局变量
        # 虽然我们现在用对象管理，但为了让 Scheduler 等组件能通过 get_runtime() 访问，
        # 我们依然设置全局单例。
        G.set_global_runtime(self.runtime)
        
        logger.info("✅ Engine started successfully.")
        return self.runtime

    async def stop(self):
        """停止系统 (原 shutdown 逻辑)"""
        logger.info("💤 Engine stopping...")
        if self.runtime and self.runtime.persister:
            try:
                await self.runtime.persister.shutdown()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        
        # 清理全局引用
        G._GLOBAL_RUNTIME = None
        self.runtime = None
        logger.info("🛑 Engine stopped.")

    # --- 上下文管理器支持 (async with) ---

    async def __aenter__(self) -> G.Runtime:
        return await self.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        if exc_type:
            logger.error(f"Engine exited with error: {exc_val}")