import asyncio
import logging
from typing import Optional

# Imports
from goose.system_config import SystemConfig
from goose.persistence import init_persistence,get_persistence,shutdown_persistence
from goose.persistence.drivers import SQLAlchemyBackend

# Events
from goose.events.bus import MemoryEventBus
from goose.events.store import SQLEventStore

# Resources
from goose.resources.store import SystemResourceStore, UserResourceStore
from goose.resources.types import ResourceKind
from goose.providers import LLMBuilder
from goose.resources.presets import get_system_presets
from goose.app.trigger_service.manager import TriggerManager
from goose.trigger.repository import TriggerRepository

# Globals
import goose.globals as G

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
        pm = init_persistence(db_url)
        # 启动数据库连接
        await pm.boot()
        
        # ==========================================
        # 2. 创建核心组件 (Core Components)
        # ==========================================
        bus = MemoryEventBus(buffer_size=self.config.event_bus_size, ttl=self.config.event_ttl)
        event_store = SQLEventStore()
        sys_store = SystemResourceStore()
        usr_store = UserResourceStore()
        trigger_store = TriggerRepository()
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
            persister=pm,
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