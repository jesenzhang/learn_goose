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
        user_id: str,
        after_seq_id: int = -1
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 启动新任务并流式返回"""
        # 1. 创建记录
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        
        # Pass after_seq_id to the orchestrator
        async for event in self._orchestrate_stream_task(
            run_id, wf_id, inputs, user_id, is_resume=False, after_seq_id=after_seq_id
        ):
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
        is_resume: bool,
        after_seq_id: int = -1
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
            # If the client requested history (e.g., -1), this will fetch from DB first
            async for event in streamer.listen(after_seq_id=after_seq_id):
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
    # 5. 异步监听 (Subscribe to Existing Run)
    # ==========================================

    async def listen_to_execution(
        self, 
        run_id: str, 
        user_id: str, 
        after_seq_id: int = -1
    ) -> AsyncGenerator[Dict, None]:
        """
        [SSE] 监听一个已经存在的执行任务 (支持断线重连/历史回放)
        
        :param run_id: 任务ID
        :param user_id: 用户ID (鉴权)
        :param after_seq_id: 从哪个序列号开始听。
               -1 表示从头开始 (History + Live)
               None 表示只听实时的 (Live Only)
               >0 表示从指定位置接续
        """
        # 1. 检查任务是否存在
        exec_record = await self.exec_repo.get(run_id)
        if not exec_record:
            raise ValueError(f"Execution {run_id} not found")

        # 2. 鉴权
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError(f"Permission denied: User {user_id} cannot access execution {run_id}")

        # 3. 获取 Streamer
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)

        # 4. 开始监听
        # Streamer.listen 内部封装了:
        # A. 如果 after_seq_id != None: 先去 EventStore 查历史事件并 yield
        # B. 订阅 EventBus 监听实时事件
        try:
            logger.info(f"🎧 Client listening to {run_id} (after seq {after_seq_id})")
            
            async for event in streamer.listen(after_seq_id=after_seq_id):
                # 序列化
                data = event.dict() if hasattr(event, "dict") else event
                yield data
                
                # 终止条件检查：如果收到了结束事件，流就该停止了
                # 这样可以防止客户端一直挂着连接，即使任务早就结束了
                event_type = data.get("type")
                if event_type in ["workflow_completed", "error", "workflow_failed"]:
                    logger.info(f"🏁 Stream {run_id} ended normally.")
                    break
                    
        except Exception as e:
            logger.error(f"Listener error for {run_id}: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
            
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