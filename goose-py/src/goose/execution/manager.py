# src/goose/app/execution/manager.py

import asyncio
import logging
from typing import Dict, Any, Optional, AsyncGenerator

from goose.globals import get_runtime
from goose.workflow.graph import Graph
from goose.workflow.scheduler import WorkflowScheduler
from goose.session.hook import SessionPersistenceHook
from goose.execution.repository import ExecutionRepository
from goose.events import IStreamer

logger = logging.getLogger("goose.execution.manager")

class ExecutionManager:
    """
    【职责】底层任务管家 (有状态)
    1. 维护 asyncio.Task 的生命周期 (启动、停止、等待)
    2. 运行 WorkflowScheduler
    3. 管理 Streamer 的发射
    """
    def __init__(self, exec_repo: ExecutionRepository):
        self.exec_repo = exec_repo
        # 内存中活跃的任务: run_id -> asyncio.Task
        self._active_tasks: Dict[str, asyncio.Task] = {}

    # --- Lifecycle Management ---

    async def start_execution(
        self, 
        run_id: str, 
        graph: Graph, 
        inputs: Dict[str, Any], 
        user_id: str, 
        is_resume: bool = False
    ):
        """
        启动（或恢复）一个后台执行任务
        注意：Manager 不需要知道 Workflow ID，它只需要 Graph 对象
        """
        if run_id in self._active_tasks:
            logger.warning(f"Task {run_id} is already running.")
            return

        # 创建后台任务
        task = asyncio.create_task(
            self._execution_loop(run_id, graph, inputs, user_id, is_resume)
        )
        self._active_tasks[run_id] = task
        
        # 3. [增强] 绑定回调，任务结束自动移除引用
        # 这样就不怕 _execution_loop 里的 finally 没跑到了（虽然 asyncio 保证 finally 会跑）
        task.add_done_callback(lambda t: self._cleanup_task(run_id))
        
        logger.info(f"🚀 Background task started for {run_id}")

    def _cleanup_task(self, run_id: str):
        """回调函数：从内存移除任务引用"""
        if run_id in self._active_tasks:
            del self._active_tasks[run_id]
            logger.debug(f"🗑️ Task {run_id} removed from memory.")
            
    async def terminate_execution(self, run_id: str):
        """强制停止任务"""
        task = self._active_tasks.get(run_id)
        if task and not task.done():
            logger.info(f"🛑 Terminating execution {run_id}...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass # Expected
            logger.info(f"🛑 Execution {run_id} terminated.")
        else:
            logger.warning(f"Task {run_id} not found in memory, marking DB as cancelled.")
            await self.exec_repo.update_status(run_id, "cancelled")

    def is_running(self, run_id: str) -> bool:
        task = self._active_tasks.get(run_id)
        return task is not None and not task.done()

    async def terminate_all(self):
        """
        [增强] 系统关闭时调用 (Graceful Shutdown)
        """
        if not self._active_tasks:
            return

        logger.info(f"🛑 Terminating {len(self._active_tasks)} active tasks...")
        
        # 1. 发送取消信号
        for task in self._active_tasks.values():
            task.cancel()
        
        # 2. 等待所有任务结束 (return_exceptions=True 防止报错)
        await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
        
        self._active_tasks.clear()
        logger.info("✅ All tasks terminated.")
        
    # --- Streaming Helpers ---

    async def listen(self, run_id: str, after_seq_id: int = -1) -> AsyncGenerator[Dict, None]:
        """
        监听指定 run_id 的事件流
        Manager 负责与 Runtime 的 StreamerFactory 交互
        """
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        
        logger.info(f"🎧 Listening to {run_id} (seq > {after_seq_id})")
        try:
            async for event in streamer.listen(after_seq_id=after_seq_id):
                # 序列化处理
                data = event.model_dump() if hasattr(event, "model_dump") else event.dict() if hasattr(event, "dict") else event
                yield data
                
                # 终止条件
                if data.get("type") in ["workflow_completed", "error", "workflow_failed", "cancelled"]:
                    break
        except Exception as e:
            logger.error(f"Listener error {run_id}: {e}")
            yield {"type": "error", "error": str(e)}

    # --- Internal Execution Loop ---

    async def _execution_loop(
        self, 
        run_id: str, 
        graph: Graph, 
        inputs: Dict, 
        user_id: str,
        is_resume: bool
    ):
        """
        [Heavy Lifting] 真正干活的地方：设置环境 -> 运行调度器 -> 清理
        """
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        
        final_status = "failed"
        error_msg = None

        try:
            # 1. Update Status
            await self.exec_repo.update_status(run_id, "running")
            
            # 2. Resource Injection
            resource_manager = runtime.create_resource_manager(user_id)
            
            # 3. Scheduler Setup
            scheduler = WorkflowScheduler(hooks=[SessionPersistenceHook()])
            
            # 4. Run
            logger.info(f"⚙️ Scheduler running for {run_id} (Resume={is_resume})")
            output = await scheduler.run(
                graph=graph,
                inputs=inputs,
                run_id=run_id,
                resource_manager=resource_manager,
                streamer=streamer,
                resume=is_resume
            )

            # 5. Success
            final_status = "completed"
            if isinstance(output, dict) and output.get("status") == "suspended":
                final_status = "suspended"
            
            await self.exec_repo.update_status(run_id, final_status, outputs=output)

        except asyncio.CancelledError:
            final_status = "cancelled"
            error_msg = "Task cancelled by user"
            logger.warning(f"🚫 Run {run_id} cancelled")
            await streamer.emit("error", {"error": error_msg})
            raise

        except Exception as e:
            final_status = "failed"
            error_msg = str(e)
            logger.error(f"❌ Run {run_id} failed: {e}", exc_info=True)
            await streamer.emit("error", {"error": error_msg})
            # 不 re-raise，否则 active_tasks 里的 task 会报 unretrieved exception

        finally:
            # 6. Cleanup
            if run_id in self._active_tasks:
                del self._active_tasks[run_id]

            # 7. Final Status Sync (Safety Net)
            if final_status in ["cancelled", "failed"]:
                await self.exec_repo.update_status(run_id, final_status, error=error_msg)
            
            # 通知 Streamer 关闭 (可选，取决于 Streamer 实现)
            # await streamer.close()