import logging
import asyncio
from typing import Optional

# 1. 配置与运行时
from goose.system_config import settings
from goose.runtime import Runtime
import goose.runtime  # 用于设置全局变量

# 2. 基础设施
from goose.persistence import init_persistence
from goose.events.bus import MemoryEventBus
from goose.events.store import SQLEventStore
from goose.events import StreamerFactory
from goose.command.bus import CommandBus

# 3. 资源系统
from goose.resources.store import SystemResourceStore, UserResourceStore
from goose.resources.types import ResourceKind
from goose.providers import LLMBuilder
from goose.resources.presets import get_system_presets

# 4. Repositories
from goose.user.repository import UserRepository, UserResourceRepository
from goose.workflow.repository import WorkflowRepository
from goose.execution.repository import ExecutionRepository
from goose.session.repository import SessionRepository
from goose.trigger.repository import TriggerRepository

# 5. Domain Components
from goose.workflow.converter import WorkflowConverter
from goose.execution.manager import ExecutionManager
from goose.trigger.manager import TriggerManager

from goose.app.execution_service import ExecutionService
from goose.app.trigger_service import TriggerService
from goose.app.workflow_service import WorkflowService
from goose.app.user_service import UserService
# from goose.app.listeners import register_listeners  # 如果有事件监听器

logger = logging.getLogger("goose.engine")

class GooseEngine:
    def __init__(self):
        self._runtime: Optional[Runtime] = None

    @property
    def runtime(self) -> Runtime:
        return self._runtime
    
    async def start(self) -> Runtime:
        logger.info("🦆 Goose Engine initializing...")

        # ==========================================
        # 1. 基础设施层 (Infrastructure Layer)
        # ==========================================
        # 数据库
        pm = init_persistence(settings.db_url)
        await pm.boot()
        
        # 总线与存储
        event_bus = MemoryEventBus(buffer_size=settings.event_bus_size, ttl=settings.event_ttl)
        command_bus = CommandBus()
        event_store = SQLEventStore()
        streamer_factory = StreamerFactory(event_bus, event_store)

        # ==========================================
        # 2. 数据访问层 (Repository Layer)
        # ==========================================
        # 这一层是无状态的，主要负责 SQL 操作
        user_repo = UserRepository()
        auth_repo = UserResourceRepository()
        wf_repo = WorkflowRepository()
        exec_repo = ExecutionRepository()
        session_repo = SessionRepository()
        trigger_repo = TriggerRepository() # TriggerManager 内部也会用到
        
        # 资源存储 (Old Architecture compat)
        sys_store = SystemResourceStore()
        usr_store = UserResourceStore()

        # ==========================================
        # 3. 核心管理层 (Manager/Worker Layer)
        # ==========================================
        # ExecutionManager: 负责底层 asyncio 任务和 Scheduler
        exec_manager = ExecutionManager(exec_repo=exec_repo)

        # TriggerManager: 暂时先创建，依赖稍后注入 (如果使用 Protocol 方式)
        # 或者直接在这里完成注入，因为它依赖的是 Protocol，我们可以传 Service
        # 但 Service 还没创建。解决方案：分步初始化。
        
        # ==========================================
        # 4. 应用服务层 (Application Service Layer)
        # ==========================================
        converter = WorkflowConverter()

        user_service = UserService(
            repo=user_repo, 
            resource_repo=auth_repo
        )
        
        wf_service = WorkflowService(
            workflow_repository=wf_repo, 
            workflow_converter=converter,
            user_resource_repository=auth_repo
        )

        # ExecutionService: 它是 Trigger 的 Runner
        exec_service = ExecutionService(
            manager=exec_manager,
            converter=converter,
            wf_repo=wf_repo,
            exec_repo=exec_repo,
            auth_repo=auth_repo,
            session_repo=session_repo
        )

        # 现在可以创建 TriggerManager 了 (注入 exec_service 作为 runner)
        trigger_manager = TriggerManager(bus=command_bus)
        
        # TriggerService: 依赖 Manager
        trigger_service = TriggerService(manager=trigger_manager)

        # ==========================================
        # 5. 系统预设与注册 (Registry)
        # ==========================================
        # 注册 LLM 构建器
        builders_registry = {
            ResourceKind.LLM: LLMBuilder()
        }

        # 加载系统预设资源
        presets = get_system_presets(settings)
        logger.info(f"📦 Registering {len(presets)} system presets...")
        for meta in presets:
            sys_store.register(meta)
            
        # ==========================================
        # 6. 启动后台进程 (Background Processes)
        # ==========================================
        # 启动触发器调度器
        await trigger_manager.start()
        
        # (可选) 恢复未完成的任务
        # await exec_manager.recover_tasks()

        # ==========================================
        # 7. 组装 Runtime 并发布
        # ==========================================
        self._runtime = Runtime(
            config=settings,
            persister=pm,
            event_bus=event_bus,
            command_bus=command_bus,
            event_store=event_store,
            streamer_factory=streamer_factory,
            
            sys_store=sys_store,
            usr_store=usr_store,
            _builders_registry=builders_registry,
            
            execution_manager=exec_manager,
            trigger_manager=trigger_manager,
            
            user_service=user_service,
            workflow_service=wf_service,
            execution_service=exec_service,
            trigger_service=trigger_service
        )

        # 设置全局单例
        goose.runtime._global_runtime = self._runtime
        
        logger.info("🚀 Goose Engine Started Successfully!")
        return self._runtime

    async def stop(self):
        logger.info("🛑 Goose Engine stopping...")
        if self._runtime:
            # 1. 停止上游 (Trigger)
            await self._runtime.trigger_manager.stop()
            
            # 2. 停止任务
            # await self._runtime.execution_manager.terminate_all()
            
            # 3. 关闭数据库
            if self._runtime.persister:
                await self._runtime.persister.shutdown()
            
            # 4. 清理引用
            goose.runtime._global_runtime = None
            self._runtime = None
            
        logger.info("💤 Engine stopped.")

    # 支持上下文管理器: async with GooseEngine() as runtime: ...
    async def __aenter__(self) -> Runtime:
        return await self.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()