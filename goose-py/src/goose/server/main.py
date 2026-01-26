import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- 1. Core & Config ---
from goose.system_config import SystemConfig
from goose.engine import GooseEngine
from goose.workflow.converter import WorkflowConverter
# --- 2. Application Layer (Services) ---
from goose.app.execution_service import ExecutionService,ExecutionManager
from goose.app.workflow_service import WorkflowService
from goose.trigger.manager import TriggerManager

# --- 3. Server Layer (Routers) ---
from goose.server.routers import workflows, executions, trigger,auth

from goose.session import SessionRepository
from goose.workflow import WorkflowRepository
from goose.app.execution_service import ExecutionRepository
from goose.app.user_service import UserRepository,UserResourceRepository
from goose.app.user_service import UserService

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("goose.server")

# 全局引用 (用于 Shutdown)
system_engine: GooseEngine = None
trigger_manager: TriggerManager = None

# ==========================================
# 🔄 Lifecycle Management (核心启动流程)
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器
    启动顺序：Config -> Engine (DB/Runtime) -> Services -> Triggers -> Server
    """
    global system_engine, trigger_manager
    
    logger.info("🌱 System Booting...")
    
    try:
        # 1. 加载配置
        config = SystemConfig()
        
        # 2. 启动 Goose Engine (基础设施层)
        # 这会初始化 DB 连接、创建表结构、设置 EventBus 和全局 Runtime
        system_engine = GooseEngine()
        await system_engine.start()
        
        
        converter = WorkflowConverter()
        
        workflow_repo = WorkflowRepository()
        execution_repo = ExecutionRepository()
        user_repo = UserRepository()
        user_resource_repo = UserResourceRepository()
        session_repo=SessionRepository()
        user_service = UserService(user_repo, user_resource_repo)
        
        workflow_service = WorkflowService(
            workflow_repository=workflow_repo,
            workflow_converter=converter,
            user_resource_repository=user_resource_repo
        )
         
        # 3. 初始化应用层服务 (Service Layer)
        # ExecutionService 依赖 Engine 初始化的全局 Runtime 和 DB
        exec_service = ExecutionService(ExecutionManager(execution_repo),
                                        converter=converter,
                                        wf_repo=workflow_repo,
                                        exec_repo=execution_repo,
                                        auth_repo=user_resource_repo,
                                        session_repo=session_repo)
        
        # 4. 初始化并启动 Trigger Manager (App Layer)
        # TriggerManager 依赖 CommandBus 来发送命令
        runtime = system_engine.runtime  # 获取运行时以获取command_bus
        trigger_manager = TriggerManager(bus=runtime.command_bus)
        await trigger_manager.start() # 加载 Cron 任务，启动调度器
        
        await user_service.get_or_create_default_user()
       
        # 5. [依赖注入] 将单例挂载到 App State
        # 这样 deps.py 里的 get_trigger_manager 就能获取到它
        app.state.trigger_manager = trigger_manager
        app.state.execution_service = exec_service
        app.state.workflow_service = workflow_service
        app.state.runtime = system_engine.runtime
        app.state.user_service =user_service
        app.state.sys_config = config
        
        logger.info("🚀 Goose Engine is Ready to serve requests!")
        yield
        
    except Exception as e:
        logger.error(f"❌ Critical error during startup: {e}", exc_info=True)
        raise e
        
    finally:
        # --- Shutdown Phase (倒序关闭) ---
        logger.info("🛑 System Shutting down...")
        
        # 6. 停止触发器 (不再接收新任务)
        if trigger_manager:
            await trigger_manager.stop()
        
        # 7. 停止引擎 (关闭 DB 连接，清理资源)
        if system_engine:
            await system_engine.stop()
            
        logger.info("👋 Bye!")

# ==========================================
# ⚡ FastAPI App Definition
# ==========================================

app = FastAPI(
    title="Goose Workflow Engine",
    description="High-performance workflow orchestration engine.",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Middleware ---

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # ⚠️ 生产环境请指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Error Handler ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"🔥 Unhandled Exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "Internal Server Error", "detail": str(exc)},
    )

# --- Router Registration ---

app.include_router(workflows.router)
app.include_router(executions.router)
app.include_router(trigger.router)
app.include_router(auth.router)
# --- Health Check ---

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "version": app.version}

# ==========================================
# 🏁 Entry Point
# ==========================================

if __name__ == "__main__":
    uvicorn.run(
        "goose.server.main:app", 
        host="0.0.0.0", 
        port=8200, 
        reload=True
    )