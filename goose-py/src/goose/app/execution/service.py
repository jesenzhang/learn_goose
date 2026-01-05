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
from goose.events import IStreamer, Event

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
        self._active_tasks: Dict[str, asyncio.Task] = {}
        
    # ==========================================
    # 1. 任务控制接口 (Public API)
    # ==========================================

    async def terminate_execution(self, run_id: str, user_id: str):
        """
        [强制停止] 取消正在运行的任务
        """
        # 1. 鉴权
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError("Permission denied")

        # 2. 检查内存中是否有该任务
        task = self._active_tasks.get(run_id)
        
        if task and not task.done():
            logger.info(f"🛑 Terminating execution {run_id}...")
            # 发送取消信号，这会在 _run_scheduler_task 内部抛出 asyncio.CancelledError
            task.cancel()
            try:
                # 等待任务完成清理
                await task
            except asyncio.CancelledError:
                pass # 预期内的异常，忽略
            logger.info(f"🛑 Execution {run_id} terminated successfully.")
        else:
            # 如果任务不在内存中（可能因为服务重启了），只更新数据库状态
            logger.warning(f"Task {run_id} not found in memory, forcing DB update.")
            await self.exec_repo.update_status(run_id, "cancelled")

    async def suspend_execution(self, run_id: str, user_id: str):
        """
        [强制挂起] 
        注意：真正的“暂停”通常需要 Scheduler 配合（在节点间隙暂停）。
        强制挂起本质上是：保存当前状态快照 -> 停止任务 -> 标记为 Suspended
        """
        # 这里简化实现：直接借用 terminate 的逻辑，但在 cleanup 时标记为 suspended
        # 更加高级的实现需要向 Scheduler 发送信号，让它在当前节点跑完后主动退出。
        # 这里演示“信号量”模式（需要 Scheduler 支持，这里先展示基础版）
        pass
    
    # ==========================================
    # 1. 核心：流式执行 (New Run & Resume)
    # ==========================================

    # ==========================================
    # 2. 流式执行 (New Run & Resume)
    # ==========================================

    async def execute_stream_generator(
        self, 
        wf_id: str, 
        inputs: Dict[str, Any], 
        user_id: str,
        after_seq_id: int = -1
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 启动新任务并流式返回"""
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        
        # 启动后台任务
        self._start_background_task(run_id, wf_id, inputs, user_id, is_resume=False)

        # 开始监听
        async for event in self._listen_to_stream(run_id, after_seq_id):
            yield event

    async def resume_stream_generator(
        self, 
        run_id: str, 
        inputs: Dict[str, Any], 
        user_id: str
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 恢复挂起任务并流式返回"""
        exec_record = await self.exec_repo.get(run_id)
        if not exec_record: raise ValueError(f"Execution {run_id} not found")
        if not await self.auth_repo.check_ownership(user_id, run_id): raise ValueError("Permission denied")

        wf_id = exec_record["workflow_id"]
        
        # 启动后台任务
        self._start_background_task(run_id, wf_id, inputs, user_id, is_resume=True)
        
        # 默认回填历史，防止丢失 Resume 前的上下文
        async for event in self._listen_to_stream(run_id, after_seq_id=-1):
            yield event

    async def listen_to_execution(
        self, 
        run_id: str, 
        user_id: str, 
        after_seq_id: int = -1
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 纯监听 (不触发运行)"""
        if not await self.exec_repo.get(run_id): raise ValueError("Not found")
        if not await self.auth_repo.check_ownership(user_id, run_id): raise ValueError("Denied")
        
        async for event in self._listen_to_stream(run_id, after_seq_id):
            yield event
            
            
    # ==========================================
    # 3. 异步执行 (Fire & Forget)
    # ==========================================

    async def run_workflow(self, wf_id: str, inputs: Dict[str, Any], user_id: str) -> str:
        """[Async] 仅触发，不等待"""
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        self._start_background_task(run_id, wf_id, inputs, user_id, is_resume=False)
        return run_id

    # ==========================================
    # 4. 内部核心逻辑 (Orchestration & Scheduling)
    # ==========================================
    def _start_background_task(self, run_id, wf_id, inputs, user_id, is_resume):
        """启动后台任务并注册到 active_tasks"""
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        
        # 创建 Task
        task = asyncio.create_task(
            self._run_scheduler_task(run_id, wf_id, inputs, user_id, streamer, is_resume)
        )
        # 注册 Task
        self._active_tasks[run_id] = task
        return task
    
    async def _listen_to_stream(self, run_id: str, after_seq_id: int) -> AsyncGenerator[Dict, None]:
        """通用监听逻辑"""
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        
        logger.info(f"🎧 Listening to {run_id} (seq > {after_seq_id})")
        try:
            async for event in streamer.listen(after_seq_id=after_seq_id):
                # 序列化
                data = event.model_dump() if hasattr(event, "model_dump") else event.dict() if hasattr(event, "dict") else event
                yield data
                
                if data.get("type") in ["workflow_completed", "error", "workflow_failed", "cancelled"]:
                    logger.info(f"🏁 Stream {run_id} ended.")
                    break
        except Exception as e:
            logger.error(f"Listener error {run_id}: {e}")
            yield {"type": "error", "error": str(e)}
            
    async def _run_scheduler_task(
        self, 
        run_id: str, 
        wf_id: str, 
        inputs: Dict, 
        user_id: str,
        streamer:'IStreamer',
        is_resume: bool
    ):
        """
        [Heavy Lifting] 包含完整的生命周期管理
        """
        runtime = get_runtime()
        # [修复 1] 预先定义变量，防止 finally 中 UnboundLocalError
        final_status = "failed"
        error_msg = None
        
        try:
            # 1. Update Status
            await self.exec_repo.update_status(run_id, "running")
            
            # 2. Prepare Environment
            graph = await self._load_and_build_graph(wf_id)
            resource_manager = runtime.create_resource_manager(user_id)
            scheduler = WorkflowScheduler(hooks=[SessionPersistenceHook()])
            
            logger.info(f"🚀 {'Resuming' if is_resume else 'Starting'} {run_id}")
            
            # 3. Run (Long-running)
            output = await scheduler.run(
                graph=graph,
                inputs=inputs,
                run_id=run_id,
                resource_manager=resource_manager,
                streamer=streamer,
                resume=is_resume
            )
            
            # 4. Success Handling
            final_status = "completed"
            if isinstance(output, dict) and output.get("status") == "suspended":
                final_status = "suspended"
            
            # 这里是正常结束的更新
            await self.exec_repo.update_status(run_id, final_status, outputs=output)
            logger.info(f"✅ Run {run_id} finished: {final_status}")

        except asyncio.CancelledError:
            # 5. Cancellation Handling
            final_status = "cancelled"
            error_msg = "Task cancelled by user"
            logger.warning(f"🚫 Run {run_id} cancelled")
            # 发送 error 事件给前端 (因为 Cancelled 不会走 streamer.emit)
            await streamer.emit("error", {"error": error_msg})
            # 重新抛出，以便 Task 状态正确标记为 Cancelled
            raise

        except Exception as e:
            # 6. Error Handling
            final_status = "failed"
            error_msg = str(e)
            logger.error(f"❌ Run {run_id} failed: {e}", exc_info=True)
            await streamer.emit("error", {"error": error_msg})
            raise

        finally:
            # 7. Cleanup (保证执行)
            # [修复 2] 由 Runner 自己负责注销，而不是由 Listener 负责
            if run_id in self._active_tasks:
                del self._active_tasks[run_id]

            # [修复 3] 只在非正常结束(或未成功更新)的情况下补救更新数据库
            # 如果上面 try 里的 update_status 成功了，这里就不需要再更新
            # 我们可以通过检查 final_status 是否为 'completed'/'suspended' 来判断是否需要补救？
            # 或者更简单：如果是 cancelled 或 failed，一定要更新。
            if final_status in ["cancelled", "failed"]:
                try:
                    await self.exec_repo.update_status(run_id, final_status, error=error_msg)
                except Exception as e:
                    logger.error(f"Failed to update final status for {run_id}: {e}")
    
    
    
    # # ==========================================
    # # 5. 异步监听 (Subscribe to Existing Run)
    # # ==========================================

    # async def listen_to_execution(
    #     self, 
    #     run_id: str, 
    #     user_id: str, 
    #     after_seq_id: int = -1
    # ) -> AsyncGenerator[Dict, None]:
    #     """
    #     [SSE] 监听一个已经存在的执行任务 (支持断线重连/历史回放)
        
    #     :param run_id: 任务ID
    #     :param user_id: 用户ID (鉴权)
    #     :param after_seq_id: 从哪个序列号开始听。
    #            -1 表示从头开始 (History + Live)
    #            None 表示只听实时的 (Live Only)
    #            >0 表示从指定位置接续
    #     """
    #     # 1. 检查任务是否存在
    #     exec_record = await self.exec_repo.get(run_id)
    #     if not exec_record:
    #         raise ValueError(f"Execution {run_id} not found")

    #     # 2. 鉴权
    #     if not await self.auth_repo.check_ownership(user_id, run_id):
    #         raise ValueError(f"Permission denied: User {user_id} cannot access execution {run_id}")

    #     # 3. 获取 Streamer
    #     runtime = get_runtime()
    #     streamer = runtime.streamer_factory.create(run_id)

    #     # 4. 开始监听
    #     # Streamer.listen 内部封装了:
    #     # A. 如果 after_seq_id != None: 先去 EventStore 查历史事件并 yield
    #     # B. 订阅 EventBus 监听实时事件
    #     try:
    #         logger.info(f"🎧 Client listening to {run_id} (after seq {after_seq_id})")
            
    #         async for event in streamer.listen(after_seq_id=after_seq_id):
    #             # 序列化
    #             data = event.model_dump() if hasattr(event, "model_dump") else event.dict() if hasattr(event, "dict") else event
    #             yield data
                
    #             # 终止条件检查：如果收到了结束事件，流就该停止了
    #             # 这样可以防止客户端一直挂着连接，即使任务早就结束了
    #             event_type = data.get("type")
    #             if event_type in ["workflow_completed", "error", "workflow_failed"]:
    #                 logger.info(f"🏁 Stream {run_id} ended normally.")
    #                 break
                    
    #     except Exception as e:
    #         logger.error(f"Listener error for {run_id}: {e}", exc_info=True)
    #         yield {"type": "error", "error": str(e)}
        

    # # ==========================================
    # # 3. 核心调度逻辑 (Unified)
    # # ==========================================

    # async def _run_scheduler_task(
    #     self, 
    #     run_id: str, 
    #     wf_id: str, 
    #     inputs: Dict, 
    #     user_id: str,
    #     streamer,
    #     is_resume: bool = False
    # ):
    #     """
    #     统一执行逻辑：负责环境准备、资源注入、调度器启动、结果保存
    #     """
    #     runtime = get_runtime()
        
    #     try:
    #         # 1. 更新状态
    #         await self.exec_repo.update_status(run_id, "running")
            
    #         # 2. 准备图 (无论是 Resume 还是 New Run，都需要图定义)
    #         graph = await self._load_and_build_graph(wf_id)
            
    #         # 3. [关键] 注入资源 (API Key, Files)
    #         # 即使是 Resume，也需要重新注入 Resource Manager，因为 Session 此时是在内存重建的
    #         resource_manager = runtime.create_resource_manager(user_id)
            
    #         # 4. 初始化调度器
    #         # SessionPersistenceHook 负责：
    #         # - New Run: 初始化 Session
    #         # - Resume: 从 DB 加载 Session 快照 (依据 run_id)
    #         scheduler = WorkflowScheduler(hooks=[SessionPersistenceHook()])
            
    #         logger.info(f"🚀 {'Resuming' if is_resume else 'Starting'} scheduler for {run_id}")
            
    #         # 5. 运行
    #         output = await scheduler.run(
    #             graph=graph,
    #             inputs=inputs,
    #             run_id=run_id,
    #             resource_manager=resource_manager,
    #             streamer=streamer,
    #             resume=is_resume # 核心标志位
    #         )
            
    #         # 6. 处理结果
    #         final_status = "completed"
    #         if isinstance(output, dict) and output.get("status") == "suspended":
    #             final_status = "suspended"
            
    #         await self.exec_repo.update_status(run_id, final_status, outputs=output)
    #         logger.info(f"✅ Scheduler finished: {final_status}")

    #     except asyncio.CancelledError:
    #         # --- 4. Cancellation Handling ---
    #         final_status = "cancelled"
    #         error_msg = "Task cancelled by user"
    #         logger.info(f"🚫 Scheduler task {run_id} cancelled")
    #         # 必须重新抛出，以便上层 orchestrator 知道任务被取消了
    #         raise
        
    #     except Exception as e:
    #         logger.error(f"❌ Scheduler error: {e}", exc_info=True)
    #         await self.exec_repo.update_status(run_id, "failed", error=str(e))
    #         raise e

    #     finally:
    #         # --- 6. Teardown / Cleanup (核心资源回收) ---
    #         # 无论什么情况（成功、失败、取消），这里都会执行
            
    #         # A. 从注册表移除
    #         if run_id in self._active_tasks:
    #             del self._active_tasks[run_id]

    #         # B. 确保数据库状态一致性 (Double Check)
    #         # 如果是 Cancelled 或 Failed，确保状态被写入
    #         if final_status in ["cancelled", "failed"]:
    #             await self.exec_repo.update_status(run_id, final_status, error=error_msg)

    #         # C. 资源释放
    #         # 如果 ResourceManager 或 Scheduler 有 close 方法，在这里调用
    #         # if hasattr(resource_manager, 'close'): await resource_manager.close()
            
    #         # D. 通知 Streamer 结束 (防止客户端挂起)
    #         # 发送一个特殊的系统事件，告诉前端连接已关闭
    #         # await streamer.emit("system", {"type": "shutdown"})
            
    #         logger.info(f"🧹 Cleanup finished for {run_id}. Final Status: {final_status}")
    
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

    async def list_active_executions(self) -> List[Dict]:
        """列出内存中正在运行的任务"""
        active_list = []
        for run_id in self._active_tasks.keys():
            # 可以去 DB 查更多详情，这里只返回 ID
            active_list.append({"run_id": run_id, "status": "running (in-memory)"})
        return active_list
    
    async def list_executions(self, wf_id: str, page: int, size: int) -> List[Dict]:
        offset = (page - 1) * size
        return await self.exec_repo.list(wf_id, size, offset)