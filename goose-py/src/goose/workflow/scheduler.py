import logging
import asyncio
from typing import Any, Optional, Dict, List, TYPE_CHECKING

# --- Core Dependencies ---
from goose.workflow.protocol import ControlSignal
from goose.workflow.graph import Graph
from goose.workflow.context import WorkflowContext
from goose.events import SystemEvents
from goose.workflow.events import WorkflowEventType
from goose.workflow.checkpointer import WorkflowCheckpointEntity, WorkflowCheckpointer
from goose.workflow.repository import WorkflowRepository

# --- Runtime Dependencies ---
from goose.globals import get_streamer_factory, get_runtime
from goose.workflow.hook import WorkflowHook

if TYPE_CHECKING:
    from goose.resources.manager import ResourceManager

logger = logging.getLogger("goose.workflow.scheduler")

class WorkflowScheduler:
    """
    [Core] 工作流调度引擎。
    负责图的遍历、节点执行、状态管理、持久化。
    """
    
    def __init__(self, 
                 checkpointer: Optional[WorkflowCheckpointer] = None,
                 hooks: List[WorkflowHook] = None # [新增] 接收钩子列表
                 ):
        # 默认使用 SQL Repository
        self._default_checkpointer = checkpointer or WorkflowRepository()
        self.hooks = hooks or [] # [新增]

    # --- 辅助方法：批量执行钩子 ---
    async def _trigger_hooks(self, method_name: str, *args, **kwargs):
        """安全地执行所有钩子"""
        for hook in self.hooks:
            try:
                # 获取对应的方法
                func = getattr(hook, method_name, None)
                if func:
                    await func(*args, **kwargs)
            except Exception as e:
                # 钩子报错不应阻断主流程，打印日志即可
                logger.error(f"🪝 Hook error in {method_name}: {e}", exc_info=True)
                
    async def run(
        self, 
        graph: Graph, 
        inputs: Any, 
        run_id: str = None, 
        streamer: Optional['Streamer'] = None,
        resume: bool = False,
        parent_ctx: WorkflowContext = None,
        resource_manager: Optional['ResourceManager'] = None,
        target_node_id: Optional[str] = None
    ) -> Any:
        """
        执行工作流。
        :return: 最终执行结果 (Final Output Dict)
        """
        
        # ==========================================
        # 1. 基础设施准备
        # ==========================================
        # 1.1 校验图
        entry_point_id = graph.entry_point
        if not entry_point_id:
             raise ValueError("Graph has no entry point!")
             
        runtime = get_runtime()
        # 1. 纯粹的 ID 生成 (不涉及数据库)
        if not run_id:
            import uuid
            run_id = uuid.uuid4().hex
            logger.info(f"🆔 Generated ephemeral run_id: {run_id}")
            
        # # 1.2 准备 Session
        # if not run_id:
        #     # 自动创建模式
        #     session = await SessionManager.create_workflow_session(name="Auto Workflow Run")
        #     run_id = session.id
        #     logger.info(f"🆕 Auto-created Workflow Session: {run_id}")
        # else:
        #     # 恢复/指定模式
        #    # [FIX] 指定 ID 模式：确保 Session 存在
        #     try:
        #         # 尝试获取 Session，如果不存在通常会抛出错误 (取决于你的 SessionManager 实现)
        #         # 或者查库返回 None
        #         session = await SessionManager.get_session(run_id)
        #         if not session:
        #             raise ValueError("Session not found")
        #         logger.info(f"🔄 Using existing session {run_id}")
        #     except Exception:
        #         # 如果 Session 不存在，必须创建它，否则后续的外键约束会报错！
        #         logger.info(f"🆕 Registering new session for provided ID: {run_id}")
        #         await SessionManager.create_session(
        #             session_id=run_id, 
        #             name=f"Run {run_id[:8]}",
        #             session_type=SessionType.WORKFLOW
        #         )
        # 1.3 获取 Streamer (Event Producer)
        if streamer is None:
            streamer = runtime.streamer_factory.create(run_id)
        
        # 1.4 兜底 Resource Manager
        if resource_manager is None:
            logger.warning("⚠️ No ResourceManager provided. Creating default (system-only).")
            resource_manager = runtime.create_resource_manager(user_id=None)

        # ==========================================
        # 2. 上下文构建与注入
        # ==========================================
        
        # 初始变量 (用于 ValueResolver)
        initial_vars = inputs if isinstance(inputs, dict) else {"input": inputs}
        
        context = WorkflowContext(
            session_id=run_id,
            parent_run_id=parent_ctx.run_id if parent_ctx else None,
            variables=initial_vars
        )
        
        # 变量继承
        if parent_ctx:
            context.variables.update(parent_ctx.variables)
            
        # [Core] 依赖注入
        context.set_services(
            resources=resource_manager,
            streamer=streamer,
            executor=self
        )

        # ==========================================
        # 3. 状态恢复与队列初始化
        # ==========================================
        queue = []
        
        if resume:
            state = await self._default_checkpointer.load_checkpoint(run_id)
            if state and state.status not in ["completed", "failed", "cancelled"]:
                logger.info(f"📥 Resuming run {run_id} from checkpoint.")
                context.node_outputs = state.context_data # 恢复内存
                if state.execution_queue:
                    queue.extend(state.execution_queue)
            else:
                logger.warning(f"⚠️ Cannot resume run {run_id}. Restarting.")

        # 初始化队列
        if not queue:
            queue.append(entry_point_id)

        # ==========================================
        # 4. 执行主循环
        # ==========================================
        
        # [Event] Workflow Started
        
        await self._trigger_hooks("on_workflow_start", run_id, inputs, context)
        await streamer.emit(SystemEvents.WORKFLOW_STARTED, inputs)
        
        
        try:
            while queue:
                current_node_id = queue.pop(0)

                # --- A. 挂起检查 ---
                if current_node_id == "__SUSPEND__":
                    logger.info(f"⏸️ Workflow {run_id} suspended.")
                    await self._save_state(run_id, queue, context, "suspended")
                    return None

                # --- B. 获取节点数据 ---
                node = graph.get_node(current_node_id)
                if not node:
                    logger.error(f"❌ Node {current_node_id} not found.")
                    continue
                
                
                # --- C. 准备组件参数 ---
                
                # [Input Logic]
                # 1. Entry Point: 接收外部真实输入 (inputs)
                # 2. Normal Node: 接收配置映射 (node.inputs)
                if current_node_id == entry_point_id:
                    # 归一化输入为字典
                    if isinstance(inputs, dict):
                        invocation_inputs = inputs
                    else:
                        invocation_inputs = {"inputs": inputs}
                else:
                    invocation_inputs = node.inputs

                # --- D. [Core] 调用无状态组件 ---
                try:
                    # 显式传递: 输入, 静态配置, 上下文
                    invocation_config = node.config.copy()
                    invocation_config["id"] = current_node_id
                    
                    await self._trigger_hooks("on_node_start", run_id, node, invocation_inputs, context)
                    # [Event] Node Started
                    await streamer.emit(
                        SystemEvents.NODE_STARTED, 
                        data={"node_type": node.component.__class__.__name__}, 
                        producer_id=current_node_id
                    )

                    output = await node.component.invoke(
                        inputs=invocation_inputs,
                        config=invocation_config,
                        context=context
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Node {current_node_id} execution failed: {e}", exc_info=True)
                    await streamer.emit(SystemEvents.NODE_ERROR, str(e), producer_id=current_node_id)
                    raise e

                # --- E. 更新上下文 ---
                if output is not None:
                    context.set_node_output(current_node_id, output)

                await self._trigger_hooks("on_node_end", run_id, node, output, context)
                # [Event] Node Finished
                await streamer.emit(
                    SystemEvents.NODE_FINISHED, 
                    data=output, 
                    producer_id=current_node_id
                )
                # --- F. 路由与控制流 ---
                
                # 1. 信号处理
                if isinstance(output, dict) and ControlSignal.SIGNAL_KEY in output:
                    signal = output[ControlSignal.SIGNAL_KEY]
                    logger.info(f"🚦 Signal: {signal}")
                    continue 
                
                # ==========================================
                # 1. 拓扑遍历 (先计算下一步去哪，确保 Queue 里有货)
                # ==========================================
                outgoing_edges = graph.get_outgoing_edges(current_node_id)
                next_nodes = []
                
                active_handle = output.get(ControlSignal.ACTIVE_HANDLE) if isinstance(output, dict) else None
                
                for edge in outgoing_edges:
                    if active_handle:
                        if edge.source_handle == active_handle:
                            next_nodes.append(edge.target)
                    elif edge.source_handle is None:
                        next_nodes.append(edge.target)

                # 入队 (简单去重)
                for nid in next_nodes:
                    if nid not in queue: 
                        queue.append(nid)

                # ==========================================
                # 2. 🎯 检查是否到达目标节点 (现在检查，支持 Resume)
                # ==========================================
                if target_node_id and current_node_id == target_node_id:
                    logger.info(f"🎯 Reached target node {target_node_id}. Stopping execution.")
                    
                    # 1. 此时 output 已经是当前节点的输出
                    # 2. 我们依然需要保存状态，以便用户查看 Context 或未来支持“从此处继续”
                    #    注意：此时 queue 里可能还有并行分支的节点，或者我们还未计算 outgoing_edges
                    #    为了支持“暂停”，建议保存当前状态 (Status: stopped/suspended)
                    
                    await self._save_state(run_id, queue, context, status="stopped")
                    
                    # 3. 发送完成事件 (或者专门的 Stopped 事件)
                    # 这里发送 COMPLETED 可能不太准确，建议前端根据 status 判断
                    await self._trigger_hooks("on_workflow_end", run_id, output, context)
                    await streamer.emit(SystemEvents.WORKFLOW_COMPLETED, output) 
                    
                    return output
                
                
                # --- G. 持久化 (Checkpoint) ---
                status_to_save = "running" if queue else "completed"
                await self._save_state(run_id, queue, context, status_to_save)

            # ==========================================
            # 5. 结束处理
            # ==========================================
            logger.info(f"🏁 Workflow {run_id} Completed.")
            
            # 提取最终结果 (Heuristic: 取最后一个节点的输出)
            # 如果 Context 里有专门标记的 outputs 也可以在这里提取
            final_output = context.node_outputs.get(current_node_id, {})
            
            
            await self._trigger_hooks("on_workflow_end", run_id, final_output, context)
            await streamer.emit(SystemEvents.WORKFLOW_COMPLETED, final_output)
            
            return final_output

        except Exception as e:
            logger.error(f"💥 Workflow {run_id} Crashed: {e}")
            await streamer.emit(SystemEvents.WORKFLOW_FAILED, str(e))
            await self._trigger_hooks("on_workflow_error", run_id, e,context)
            # 保存失败状态
            retry_queue = [current_node_id] + queue
            await self._save_state(run_id, retry_queue, context, "failed")
            raise e

    # ==========================================
    # Helpers
    # ==========================================

    async def _save_state(self, run_id: str, queue: List[str], context: WorkflowContext, status: str):
        """持久化状态辅助方法"""
        if self._default_checkpointer:
            state = WorkflowCheckpointEntity(
                run_id=run_id,
                execution_queue=queue,
                context_data=context.node_outputs, 
                status=status
            )
            await self._default_checkpointer.save_checkpoint(state)

    async def run_to_completion(
        self, 
        inputs: Dict[str, Any], 
        parent_ctx: Optional[WorkflowContext] = None,
        graph: Graph = None # 需要传入子图
    ) -> Dict[str, Any]:
        """
        [Helper] 运行子图直到结束，并直接返回结果。
        因为 run 现在是普通的 awaitable，所以这里直接 await 即可。
        """
        if not graph:
            raise ValueError("Sub-workflow graph must be provided")

        # 子工作流使用父级的资源管理器 (同用户)，但独立的 run_id
        return await self.run(
            graph=graph,
            inputs=inputs,
            parent_ctx=parent_ctx,
            resource_manager=parent_ctx.resources if parent_ctx else None
        )