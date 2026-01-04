import asyncio
import uuid
import logging
from typing import Dict, Any, AsyncGenerator,List,Optional
import json
# Core Modules
import goose.globals as G
from goose.workflow.graph import Graph
from goose.workflow.scheduler import WorkflowScheduler
from goose.workflow.converter import WorkflowConverter
from goose.adapter import AdapterManager
from goose.workflow import WorkflowDefinition, WorkflowRepository
from goose.session.hook import SessionPersistenceHook
from goose.globals import get_runtime

# Repositories
from goose.app.user.repository import UserResourceRepository
from .repository import ExecutionRepository

logger = logging.getLogger("goose.app.execution")


class ExecutionService:
    def __init__(self, 
                 converter: WorkflowConverter,
                 wf_repo: WorkflowRepository,
                 exec_repo: ExecutionRepository,
                 auth_repo: UserResourceRepository):
        self.wf_repo = wf_repo
        self.exec_repo = exec_repo
        self.converter = converter
        self.auth_repo = auth_repo


        
    async def get_execution(self, run_id: str) -> Dict[str, Any]:
        """获取详情"""
        res = await self.exec_repo.get(run_id)
        if not res:
            raise ValueError("Execution not found")
        return res

    async def list_executions(self, wf_id: str, page: int, size: int) -> List[Dict[str, Any]]:
        """获取历史列表"""
        offset = (page - 1) * size
        return await self.exec_repo.list(wf_id, size, offset)
    
    async def resume_workflow(self, run_id: str, inputs: Dict[str, Any] = None) -> None:
        """
        [业务逻辑] 恢复暂停/失败的任务
        """
        # 1. 检查任务是否存在
        exec_record = await self.exec_repo.get(run_id)
        if not exec_record:
            raise ValueError(f"Execution {run_id} not found")

        wf_id = exec_record["workflow_id"]
        graph = await self._prepare_run(wf_id)
        
        # 2. 更新状态 (Optional: 如果传入了新 inputs，可能需要合并到 Context)
        # 这里简化处理，inputs 仅用于更新 Context，具体由 Scheduler 处理
        
        # 3. 启动调度器 (Resume Mode)
        session_hook = SessionPersistenceHook()
        scheduler = WorkflowScheduler(hooks=[session_hook])
        
        # 这里的关键是 resume=True
        asyncio.create_task(scheduler.run(
            graph=graph, 
            inputs=inputs or {}, # 这里传入的 inputs 会合并到 context
            run_id=run_id, 
            resume=True
        ))
        
        logger.info(f"🔄 Execution resumed: {run_id}")

    async def test_single_node(self, node_type: str, config: Dict, inputs: Dict, mock_ctx: Dict) -> Any:
        """
        [调试逻辑] 运行单个节点，不涉及工作流持久化
        """
        runtime = get_runtime()
        
        # 1. 工厂创建组件实例
        # 假设 runtime 有 component_factory (或者 resource_manager)
        # 这里演示手动从 ResourceKind/Registry 加载
        # 实际代码可能：component = runtime.component_factory.create(node_type)
        from goose.resources.factory import create_component_by_type # 假设你有这个工厂方法
        component = create_component_by_type(node_type)
        
        if not component:
            raise ValueError(f"Unknown node type: {node_type}")

        # 2. 构建临时上下文
        temp_run_id = f"test_{uuid.uuid4().hex[:6]}"
        context = WorkflowContext(
            session_id=temp_run_id,
            variables=mock_ctx
        )
        # 注入依赖 (Resource, etc.)
        context.set_services(resources=get_resource_manager(), streamer=None, executor=None)

        # 3. 执行
        # 加上 config['id'] 避免组件报错
        if "id" not in config: config["id"] = "test_node"
        
        output = await component.invoke(inputs, config, context)
        return output

    async def get_event_generator(self, run_id: str, last_event_id: int = -1) -> AsyncGenerator:
        """
        [Stream Logic] 获取事件流
        支持：历史回填 (Backfill) + 实时监听 (Realtime)
        """
        # 1. 验证 run_id 存在
        if not await self.exec_repo.get(run_id):
            raise ValueError("Execution not found")

        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        
        # Streamer.listen 内部封装了 "先查 DB events 表，再监听 Bus" 的逻辑
        async for event in streamer.listen(after_seq_id=last_event_id):
            yield event

    async def get_execution_detail(self, run_id: str) -> Dict:
        data = await self.exec_repo.get(run_id)
        if not data:
            raise ValueError("Execution not found")
        return data
    
    
    
    
    # ==========================================
    # 1. 核心：流式执行 (解决竞态条件)
    # ==========================================
    
    async def execute_stream_generator(
        self, 
        wf_id: str, 
        inputs: Dict[str, Any], 
        user_id: str
    ) -> AsyncGenerator[Dict, None]:
        """
        [SSE 入口] 创建任务并返回事件流
        采用 Queue 缓冲模式，确保在任务启动前监听器已就绪。
        """
        # 1. 鉴权与初始化记录
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        
        # 2. 准备组件
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)
        
        # 3. 创建缓冲队列 (核心优化点)
        # 作用：作为 EventBus 和 HTTP Response 之间的桥梁
        event_queue = asyncio.Queue()

        # 4. 定义后台执行任务
        async def background_runner():
            try:
                # 真正的业务逻辑执行
                await self._run_scheduler_task(run_id, wf_id, inputs, user_id, streamer)
            except Exception as e:
                logger.error(f"Background runner failed: {e}", exc_info=True)
                await streamer.emit("error", {"error": str(e)})
            finally:
                # 任务结束（无论成功失败），给队列发一个 None 哨兵，通知消费者停止
                await event_queue.put(None)

        # 5. 定义监听任务
        # 作用：把 Streamer 收到的消息搬运到 Queue 里
        async def event_listener():
            async for event in streamer.listen():
                await event_queue.put(event)
        
        # 6. 启动双任务
        # 关键：先启动监听，再启动执行。虽然是并发，但 Queue 保证了消息不会丢。
        listener_task = asyncio.create_task(event_listener())
        runner_task = asyncio.create_task(background_runner())

        # 7. 消费队列 (HTTP 响应生成器)
        try:
            while True:
                # 等待队列消息
                event = await event_queue.get()
                
                # 收到哨兵 None，说明任务结束
                if event is None:
                    break
                
                # 格式化并 Yield 给前端
                # 如果 event 是 Pydantic 对象，转 dict
                data = event.dict() if hasattr(event, "dict") else event
                yield data
                
                # 如果是终止事件，可以提前跳出（双重保险）
                event_type = data.get("type")
                if event_type in ["workflow_completed", "error", "workflow_failed"]:
                    break
                    
        except asyncio.CancelledError:
            logger.warning(f"Client disconnected stream {run_id}")
            # 客户端断开连接，取消后台任务 (可选，视业务需求而定)
            # runner_task.cancel()
            raise

    
    # ==========================================
    # 2. 普通异步执行 (Fire & Forget)
    # ==========================================

    async def run_workflow(self, wf_id: str, inputs: Dict[str, Any], user_id: str) -> str:
        """
        [API 入口] 仅触发任务，立即返回 ID
        """
        # 1. 初始化
        run_id = await self._create_execution_record(wf_id, inputs, user_id)
        
        # 2. 获取 Runtime Streamer (即使不流式输出，Scheduler 内部也需要它来发事件)
        runtime = get_runtime()
        streamer = runtime.streamer_factory.create(run_id)

        # 3. 丢进后台运行
        asyncio.create_task(
            self._run_scheduler_task(run_id, wf_id, inputs, user_id, streamer)
        )
        
        return run_id
    
    # ==========================================
    # 3. 内部核心逻辑 (原子化封装)
    # ==========================================

    async def _create_execution_record(self, wf_id: str, inputs: Dict, user_id: str) -> str:
        """Helper: 鉴权并创建 DB 记录"""
        # A. 鉴权
        if not await self.auth_repo.check_ownership(user_id, wf_id):
            raise ValueError(f"Permission denied: User {user_id} cannot access workflow {wf_id}")

        # B. 创建 ID
        run_id = f"run_{uuid.uuid4().hex}"
        
        # C. 存库
        await self.exec_repo.create(run_id, wf_id, inputs)
        await self.auth_repo.bind(user_id, run_id, "execution")
        
        return run_id

    async def _run_scheduler_task(
        self, 
        run_id: str, 
        wf_id: str, 
        inputs: Dict, 
        user_id: str,
        streamer
    ):
        """
        [Heavy Lifting] 真正的调度逻辑
        包含：状态更新、资源加载、图构建、运行、结果保存
        """
        runtime = get_runtime()
        
        try:
            # 1. 更新状态 -> Running
            await self.exec_repo.update_status(run_id, "running")
            
            # 2. 准备 Graph
            # 这里需要从 WorkflowRepo 加载定义，转换成 Graph 对象
            # 假设你有一个 helper 方法做这个事
            graph = await self._load_and_build_graph(wf_id)
            
            # 3. 准备资源管理器 (注入用户 API Key)
            resource_manager = runtime.create_resource_manager(user_id)
            
            # 4. 初始化调度器
            # SessionHook 用于节点执行完后保存中间状态
            scheduler = WorkflowScheduler(hooks=[SessionPersistenceHook()])
            
            logger.info(f"🚀 Scheduler starting for {run_id}")
            
            # 5. 执行 (Await until finish)
            output = await scheduler.run(
                graph=graph,
                inputs=inputs,
                run_id=run_id,
                resource_manager=resource_manager,
                streamer=streamer # 传入 Streamer 供节点发送 token
            )
            
            # 6. 处理结果
            # 判断是暂停(suspended)还是完成(completed)
            final_status = "completed"
            if isinstance(output, dict) and output.get("status") == "suspended":
                final_status = "suspended"
            
            # 7. 更新 DB -> Completed
            # 注意：outputs 最好转成 JSON 字符串存库
            await self.exec_repo.update_status(
                run_id, 
                final_status, 
                result=output
            )
            logger.info(f"✅ Scheduler finished for {run_id}: {final_status}")

        except Exception as e:
            logger.error(f"❌ Scheduler failed for {run_id}: {e}", exc_info=True)
            # 更新 DB -> Failed
            await self.exec_repo.update_status(run_id, "failed", error=str(e))
            # 确保错误也能通过 SSE 发出去
            await streamer.emit("error", {"error": str(e)})
            raise e

    # ==========================================
    # 4. 辅助方法
    # ==========================================

    async def _load_and_build_graph(self, wf_id: str) -> Graph:
        """加载工作流定义并转换为图对象"""
        
        wf_def = await self.wf_repo.get(wf_id)
        if not wf_def:
            raise ValueError(f"Workflow {wf_id} not found")
        
        # Definition -> Graph
        return self.converter.convert(wf_def)

