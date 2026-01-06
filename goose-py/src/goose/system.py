import asyncio
from typing import Optional

# Imports
from goose.system_config import SystemConfig
from goose.persistence.manager import persistence_manager
from goose.persistence.drivers import SQLAlchemyBackend
from goose.registry import sys_registry
# Events
from goose.events.bus import MemoryEventBus  # [修正] 导入具体实现
from goose.events.store import SQLEventStore

# Resources
from goose.resources.store import SystemResourceStore, UserResourceStore
from goose.resources.types import ResourceKind
from goose.providers import LLMBuilder

# Globals
import goose.globals as G

# # Modules schemas (用于 JIT 注册)
# from goose.session import register_session_schemas
from goose.resources.presets import get_system_presets
# from goose.events import register_event_store_schema

async def boot(config: SystemConfig = None) -> G.Runtime:
    if config is None:
        config = SystemConfig()

    # 1. 初始化持久层
    db_path = config.db_url
    if not db_path.startswith("sqlite") and not "://" in db_path:
            # 假设是相对文件路径
            db_url = f"sqlite+aiosqlite:///{db_path}"
    else:
            db_url = db_path
    backend = SQLAlchemyBackend(db_url)
    
    # [修正] persistence_manager 是单例对象，不是类
    persistence_manager.set_backend(backend)
    
    # 注册各个模块的 Schema (利用 PM 的 Lazy Loading 特性)
    # register_session_schemas()
    # register_event_store_schema()
    
    await persistence_manager.boot()
    
    # 2. 创建核心组件
    # [修正] 必须实例化具体的 MemoryEventBus
    bus = MemoryEventBus(buffer_size=config.event_bus_size, ttl=config.event_ttl)

    # 事件存储 (依赖注入 PM)
    event_store = SQLEventStore(persistence_manager)
    
    # 资源存储 (System 无状态，User 依赖 PM)
    sys_store = SystemResourceStore()
    usr_store = UserResourceStore(persistence_manager)

    # 3. 创建 Streamer 工厂 (注入 Bus 和 EventStore)
    # 注意：BaseStreamer 需要的是 IStreamPersister 接口，SQLEventStore 实现了它
    factory = G.StreamerFactory(bus, event_store)
    
    presets = get_system_presets(config)
    
    print(f"📦 Registering {len(presets)} system resources...")
    for meta in presets:
        sys_store.register(meta)
    
    # 4. [核心] 打包成 Runtime
    runtime = G.Runtime(
        config=config,
        bus=bus,
        persister=persistence_manager, # 全局 PM
        event_store=event_store,       # 专用 Event Store
        streamer_factory=factory,
        sys_store=sys_store,           # [修正] 补充缺失参数
        usr_store=usr_store,           # [修正] 补充缺失参数
    )
    
    # 5. 注册全局资源构建器
    runtime.register_global_builder(ResourceKind.LLM, LLMBuilder())
    
    # 6. 存入全局变量
    G.set_global_runtime(runtime)
    
    print("✅ Goose System Booted Successfully.")
    return runtime

async def shutdown():
    """清理资源"""
    try:
        # 获取当前运行时
        runtime = G.get_runtime()
        if runtime.persister:
            await runtime.persister.shutdown()
            
        # 清理全局引用 (重置为 None)
        G._GLOBAL_RUNTIME = None
        print("💤 Goose System Shutdown.")
        
    except RuntimeError:
        pass # System not booted, ignore