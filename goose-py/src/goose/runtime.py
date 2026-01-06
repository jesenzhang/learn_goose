from dataclasses import dataclass, field
from typing import Optional, Dict

# Config
from goose.system_config import SystemConfig

# Infrastructure
from goose.persistence.manager import PersistenceManager
from goose.events import IEventBus, IEventStore
from goose.events import StreamerFactory
from goose.command.bus import CommandBus

# Resource Management (旧架构保留)
from goose.resources.store import ResourceStore
from goose.resources.manager import ResourceManager
from goose.resources.builder import ResourceBuilder

# Domain Services (新架构引入)
from goose.app.user_service import UserService
from goose.app.execution_service import ExecutionService
from goose.execution.manager import ExecutionManager
from goose.app.trigger_service import TriggerService
from goose.trigger.manager import TriggerManager
from goose.app.workflow_service import WorkflowService

@dataclass
class Runtime:
    """
    Goose 运行时容器：持有所有单例组件
    """
    # 1. 基础配置与设施
    config: SystemConfig
    persister: PersistenceManager
    event_bus: IEventBus
    command_bus: CommandBus
    event_store: IEventStore
    
    # 2. 核心工厂
    streamer_factory: StreamerFactory
    
    # 3. 资源管理 (Resource System)
    sys_store: ResourceStore
    usr_store: ResourceStore
    _builders_registry: Dict[str, ResourceBuilder] = field(default_factory=dict)
    
    # 4. 后台管理器 (Workers)
    execution_manager: ExecutionManager
    trigger_manager: TriggerManager
    
    # 5. 业务服务 (Facades)
    user_service: UserService
    workflow_service: WorkflowService
    execution_service: ExecutionService
    trigger_service: TriggerService

    def register_global_builder(self, kind: str, builder: ResourceBuilder):
        """注册全局资源构建器 (如 LLM)"""
        self._builders_registry[kind] = builder
        
    def create_resource_manager(self, user_id: str = None) -> ResourceManager:
        """工厂方法：为当前请求创建资源管理器"""
        rm = ResourceManager(
            system_store=self.sys_store,
            user_store=self.usr_store,
            user_id=user_id
        )
        # 注入全局 Builder
        for kind, builder in self._builders_registry.items():
            rm.register_builder(kind, builder)
        return rm

# --- 全局访问点 ---
_global_runtime: Optional[Runtime] = None

def get_runtime() -> Runtime:
    if _global_runtime is None:
        raise RuntimeError("Goose Engine not started! Call engine.start() first.")
    return _global_runtime