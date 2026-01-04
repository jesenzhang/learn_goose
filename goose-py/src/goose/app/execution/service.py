import asyncio
import uuid
import logging
import json
from typing import Dict, Any, AsyncGenerator, List, Optional

# Core Modules
from goose.globals import get_runtime
from goose.workflow.graph import Graph
from goose.workflow.scheduler import WorkflowScheduler
from goose.workflow.converter import WorkflowConverter
from goose.session.hook import SessionPersistenceHook
from goose.resources.manager import ResourceManager

# Repositories
from goose.app.user.repository import UserResourceRepository
from .repository import ExecutionRepository
from goose.workflow.repository import WorkflowRepository
from goose.session.repository import SessionRepository

logger = logging.getLogger("goose.app.execution")

class ExecutionService:
    def __init__(
        self, 
        converter: WorkflowConverter,
        wf_repo: WorkflowRepository,
        exec_repo: ExecutionRepository,
        auth_repo: UserResourceRepository,
        session_repo: SessionRepository = None
    ):
        self.wf_repo = wf_repo
        self.exec_repo = exec_repo
        self.auth_repo = auth_repo
        self.session_repo = session_repo
        self.converter = converter

    # ==========================================
    # 1. 核心：流式执行 (New Run & Resume)
    # ==========================================

    async def execute_stream_generator(
        self, 
        wf_id: str, 
        inputs: Dict[str, Any], 
        user_id: str
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 启动新任务并流式返回"""
        # 1. 创建记录
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        
        # 2. 编排流式任务 (New Run)
        async for event in self._orchestrate_stream_task(run_id, wf_id, inputs, user_id, is_resume=False):
            yield event

    async def resume_stream_generator(
        self, 
        run_id: str, 
        inputs: Dict[str, Any], 
        user_id: str
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 恢复挂起任务并流式返回"""
        # 1. 校验与获取信息
        exec_record = await self.exec_repo.get(run_id)
        if not exec_record:
            raise ValueError(f"Execution {run_id} not found")
        
        # 鉴权
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError("Permission denied")

        wf_id = exec_record["workflow_id"]
        
        # 2. 编排流式任务 (Resume)
        async for event in self._orchestrate_stream_task(run_id, wf_id, inputs, user_id, is_resume=True):
            yield event

    async def _orchestrate_stream_task(
        self, 
        run_id: str, 
        wf_id: str, 
        inputs: Dict, 
        user_id: str,
        is_resume: bool
    ) -> AsyncGenerator[Dict, None]:
        """
        [Core Helper] 统一处理 New Run 和 Resume 的流式编排
        使用 Queue 模式解决竞态条件。
        """
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        event_queue = asyncio.Queue()

        # A. 定义后台任务
        async def background_runner():
            try:
                await self._run_scheduler_task(
                    run_id=run_id, 
                    wf_id=wf_id, 
                    inputs=inputs, 
                    user_id=user_id, 
                    streamer=streamer,
                    is_resume=is_resume
                )
            except Exception as e:
                logger.error(f"Runner failed: {e}", exc_info=True)
                await streamer.emit("error", {"error": str(e)})
            finally:
                await event_queue.put(None) # 哨兵

        # B. 定义监听任务
        async def event_listener():
            # 这里可以根据 is_resume 决定是否加载历史事件，通常 Resume 只需要监听新的
            async for event in streamer.listen():
                await event_queue.put(event)

        # C. 启动
        listener_task = asyncio.create_task(event_listener())
        runner_task = asyncio.create_task(background_runner())

        # D. 消费与 Yield
        try:
            while True:
                event = await event_queue.get()
                if event is None: break
                
                # 序列化处理
                data = event.dict() if hasattr(event, "dict") else event
                yield data
                
                # 终止检测
                if data.get("type") in ["workflow_completed", "error", "workflow_failed"]:
                    break
        except asyncio.CancelledError:
            logger.warning(f"Stream disconnected: {run_id}")
            # runner_task.cancel() # 可选：客户端断开是否取消任务
            raise

    # ==========================================
    # 2. 异步执行 (Fire & Forget)
    # ==========================================

    async def run_workflow(self, wf_id: str, inputs: Dict[str, Any], user_id: str) -> str:
        """[Async] 仅触发，不等待"""
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)

        asyncio.create_task(
            self._run_scheduler_task(run_id, wf_id, inputs, user_id, streamer, is_resume=False)
        )
        return run_id

    # ==========================================
    # 3. 核心调度逻辑 (Unified)
    # ==========================================

    async def _run_scheduler_task(
        self, 
        run_id: str, 
        wf_id: str, 
        inputs: Dict, 
        user_id: str,
        streamer,
        is_resume: bool = False
    ):
        """
        统一执行逻辑：负责环境准备、资源注入、调度器启动、结果保存
        """
        runtime = get_runtime()
        
        try:
            # 1. 更新状态
            await self.exec_repo.update_status(run_id, "running")
            
            # 2. 准备图 (无论是 Resume 还是 New Run，都需要图定义)
            graph = await self._load_and_build_graph(wf_id)
            
            # 3. [关键] 注入资源 (API Key, Files)
            # 即使是 Resume，也需要重新注入 Resource Manager，因为 Session 此时是在内存重建的
            resource_manager = runtime.create_resource_manager(user_id)
            
            # 4. 初始化调度器
            # SessionPersistenceHook 负责：
            # - New Run: 初始化 Session
            # - Resume: 从 DB 加载 Session 快照 (依据 run_id)
            scheduler = WorkflowScheduler(hooks=[SessionPersistenceHook()])
            
            logger.info(f"🚀 {'Resuming' if is_resume else 'Starting'} scheduler for {run_id}")
            
            # 5. 运行
            output = await scheduler.run(
                graph=graph,
                inputs=inputs,
                run_id=run_id,
                resource_manager=resource_manager,
                streamer=streamer,
                resume=is_resume # 核心标志位
            )
            
            # 6. 处理结果
            final_status = "completed"
            if isinstance(output, dict) and output.get("status") == "suspended":
                final_status = "suspended"
            
            await self.exec_repo.update_status(run_id, final_status, outputs=output)
            logger.info(f"✅ Scheduler finished: {final_status}")

        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}", exc_info=True)
            await self.exec_repo.update_status(run_id, "failed", error=str(e))
            raise e

    # ==========================================
    # 4. 辅助与 CRUD
    # ==========================================

    async def _create_execution_record(self, wf_id: str, inputs: Dict, user_id: str) -> str:
        if not await self.auth_repo.check_ownership(user_id, wf_id):
            raise ValueError("Permission denied")
        
        run_id = f"run_{uuid.uuid4().hex}"
        await self.session_repo.create_session(session_id=run_id, name="New Session", metadata={
                "user_id": user_id,
                "workflow_id": wf_id
            })
        await self.exec_repo.create(run_id, wf_id, inputs)
        await self.auth_repo.bind(user_id, run_id, "execution")
        return run_id

    async def _load_and_build_graph(self, wf_id: str) -> Graph:
        wf_def = await self.wf_repo.get(wf_id)
        if not wf_def: raise ValueError("Workflow not found")
        return self.converter.convert(wf_def)

    async def get_execution(self, run_id: str) -> Dict:
        res = await self.exec_repo.get(run_id)
        if not res: raise ValueError("Execution not found")
        return res

    async def list_executions(self, wf_id: str, page: int, size: int) -> List[Dict]:
        offset = (page - 1) * size
        return await self.exec_repo.list(wf_id, size, offset)