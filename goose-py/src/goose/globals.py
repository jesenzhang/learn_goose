from dataclasses import dataclass, field
from typing import Optional, Type, TypeVar, Dict, Callable, Any

from goose.config import SystemConfig
from goose.events import IEventBus, IEventStore
from goose.events.streamer import BaseStreamer
from goose.persistence.manager import PersistenceManager
from goose.resources.manager import ResourceManager
from goose.resources.store import ResourceStore
from goose.resources.builder import ResourceBuilder
from goose.container import IoCContainer

T = TypeVar("T", bound=BaseStreamer)

class ExtensionContainer(IoCContainer):
    """存放插件或非核心组件"""
    pass

class StreamerFactory:
    """
    负责生产绑定到特定 run_id 的 Streamer 实例。
    """
    def __init__(self, bus: IEventBus, store: IEventStore):
        self._bus = bus
        self._store = store

    def create(self, run_id: str, streamer_cls: Type[T] = BaseStreamer) -> T:
        return streamer_cls(
            run_id=run_id,
            bus=self._bus,
            store=self._store
        )

# --- 1. 定义运行时的"全貌" ---
@dataclass(frozen=True)
class Runtime:
    # Infrastructure
    config: SystemConfig
    bus: IEventBus
    persister: PersistenceManager  # 持久层管理器单例
    event_store: IEventStore       # 事件存储专用接口
    
    # Factory
    streamer_factory: StreamerFactory
    
    # Resource Management
    sys_store: ResourceStore
    usr_store: ResourceStore
    
    # Registry: 字典是可变对象，即使 Runtime 是 frozen 的，字典内容也可以修改
    _builders_registry: Dict[str, ResourceBuilder] = field(default_factory=dict)
    
    # Extensions
    extensions: ExtensionContainer = field(default_factory=ExtensionContainer)

    def is_production(self) -> bool:
        return self.config.env == "production"
    
    def register_global_builder(self, kind: str, builder: ResourceBuilder):
        """注册全局资源构建器"""
        self._builders_registry[kind] = builder
        
    def create_resource_manager(self, user_id: str = None) -> ResourceManager:
        """
        [Factory Method]
        为当前请求创建一个绑定了 user_id 的 Manager
        """
        rm = ResourceManager(
            system_store=self.sys_store,
            user_store=self.usr_store,
            user_id=user_id
        )
        
        # 注入全局注册的 Builders
        for kind, builder in self._builders_registry.items():
            rm.register_builder(kind, builder)
            
        return rm

# --- 2. 全局单例容器 ---
_GLOBAL_RUNTIME: Optional[Runtime] = None

# --- 3. 初始化入口 (给 system.py 用的) ---
def set_global_runtime(runtime: Runtime):
    global _GLOBAL_RUNTIME
    if _GLOBAL_RUNTIME is not None:
        raise RuntimeError("Runtime already initialized!")
    _GLOBAL_RUNTIME = runtime

# --- 4. 访问入口 (给业务代码用的) ---
def get_runtime() -> Runtime:
    if _GLOBAL_RUNTIME is None:
        raise RuntimeError("System not booted. Call system.boot() first.")
    return _GLOBAL_RUNTIME

# --- 5. 便捷代理 ---
def get_bus() -> IEventBus:
    return get_runtime().bus

def get_streamer_factory() -> StreamerFactory:
    return get_runtime().streamer_factory

def get_resource_manager(user_id: str) -> ResourceManager:
    return get_runtime().create_resource_manager(user_id)