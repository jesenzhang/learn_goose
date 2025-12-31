import logging
import asyncio
from typing import Any, AsyncGenerator, Optional, Dict, Union, List

# 引用核心依赖
from goose.workflow.protocol import ControlSignal
from goose.workflow.graph import Graph
from goose.workflow.context import WorkflowContext
from goose.workflow.events import (
    WorkflowEvent, WorkflowEventType, 
    NodeEvent, NodeFinishedEvent, WorkflowCompletedEvent
)
from goose.workflow.persistence import WorkflowState, WorkflowCheckpointer
from goose.session import SessionManager, SessionType
from goose.workflow.repository import WorkflowRepository, register_workflow_schemas

from goose.globals import get_streamer_factory, get_runtime

logger = logging.getLogger("goose.workflow.scheduler")

class WorkflowScheduler:
    """
    [Core] 工作流调度引擎。
    负责图的遍历、节点执行、状态管理、持久化和事件分发。
    """
    def __init__(self, graph: Graph, checkpointer: Optional[WorkflowCheckpointer] = None):
        self.graph = graph
        # 确保数据库 Schema 已就绪
        register_workflow_schemas()
        # 默认使用基于 SQLite 的 Repository
        self.checkpointer = checkpointer or WorkflowRepository()

    async def run(
        self, 
        input_data: Any, 
        run_id: str = None, 
        resume: bool = False,
        parent_ctx: WorkflowContext = None,
        resource_manager: Optional['ResourceManager'] = None
    ) -> Any:
        """
        执行工作流。
        :param input_data: 初始输入数据
        :param run_id: 会话 ID (Session ID)
        :param resume: 是否从断点恢复
        :param parent_ctx: 父级上下文 (用于子工作流变量继承)
        """
        # 1. 找到入口 ID
        entry_point_id = self.graph.entry_point
        if not entry_point_id:
             raise ValueError("Graph has no entry point!")
         
        runtime = get_runtime()
        # ==========================================
        # 1. 初始化 Session & Context
        # ==========================================
        should_inject_start = False
        
        if not run_id:
            # 自动创建模式
            session = await SessionManager.create_workflow_session(name="Auto Workflow Run")
            run_id = session.id
            should_inject_start = True
            logger.info(f"🆕 Auto-created Workflow Session: {run_id}")
        else:
            # 指定 ID 模式 (Resume 或 子图)
            try:
                await SessionManager.get_session(run_id)
                if resume:
                    logger.info(f"🔄 Resuming session {run_id}")
                    should_inject_start = False
                else:
                    logger.info(f"🔄 Restarting session {run_id}")
                    should_inject_start = True
            except ValueError:
                # Session 不存在，强制创建 (通常用于子图)
                await SessionManager.create_session(
                    session_id=run_id, 
                    name=f"Sub-Workflow {run_id[-6:]}", 
                    session_type=SessionType.WORKFLOW
                )
                should_inject_start = True

        # B. 获取 Streamer
        streamer = runtime.streamer_factory.create(run_id)
        # C. 兜底 Resource Manager (防止调用方未传)
        if resource_manager is None:
            logger.warning("⚠️ No ResourceManager provided. Creating default (system-only).")
            resource_manager = runtime.create_resource_manager(user_id=None)
        
        # ==========================================
        # 2. 上下文构建与注入
        # ==========================================
        
        # 初始变量 (用于 ValueResolver 解析全局变量 {{ var }})
        initial_vars = input_data if isinstance(input_data, dict) else {"input": input_data}
        
        context = WorkflowContext(
            run_id=run_id,
            parent_run_id=parent_ctx.run_id if parent_ctx else None,
            variables=initial_vars
        )
        # [Feature] 变量继承: 将父级上下文变量复制到当前上下文
        if parent_ctx:
            context.variables.update(parent_ctx.variables)
            
        context.set_services(
            resources=resource_manager,
            streamer=streamer,
            executor=self
        )
        
        # ==========================================
        # 2. 状态恢复与队列初始化
        # ==========================================
        queue = [] # BFS 执行队列
        
        if resume and self.checkpointer:
            state = await self.checkpointer.load_checkpoint(run_id)
            if state and state.status not in ["completed", "failed", "cancelled"]:
                logger.info(f"📥 Checkpoint loaded. Resuming from node: {state.current_node_id}")
                # 恢复上下文数据
                context.node_outputs = state.context_data
                
                # 恢复执行队列
                # 注意: 当前架构 WorkflowState 仅存储单个 current_node_id
                # 这意味着如果崩溃时队列中有多个并行节点，只能恢复头部的一个
                # TODO: 升级 WorkflowState 支持 queue: List[str] 以支持完美并行恢复
                if state.execution_queue:
                    queue.extend(state.execution_queue)
                    logger.info(f"📥 Resuming {len(queue)} nodes: {queue}")
                else:
                    # 兼容性：如果状态是 running 但队列为空，可能是旧数据或异常
                    logger.warning("⚠️ Resuming running state but queue is empty.")
                
                should_inject_start = False
            else:
                logger.warning(f"⚠️ Checkpoint invalid or completed. Restarting from scratch.")
                should_inject_start = True

        # 如果队列为空（新运行或恢复失败），从 Entry Point 开始
        if not queue:
            if self.graph.entry_point:
                queue.append(self.graph.entry_point)
            else:
                logger.warning("🚫 No entry point found in Graph. Workflow might be empty.")

        
        # 发送开始事件
        await streamer.emit(type=WorkflowEventType.WORKFLOW_STARTED, data=run_id)

        try:
            # ==========================================
            # 3. 执行主循环 (Execution Loop)
            # ==========================================
            while queue:
                current_node_id = queue.pop(0)
                
                # --- A. 挂起控制 ---
                if current_node_id == "__SUSPEND__":
                    logger.info(f"⏸️ Workflow {run_id} suspended.")
                    await self._save_state(run_id, current_node_id, context, "suspended")
                    return

                # --- B. 获取节点实例 ---
                node = self.graph.get_node(current_node_id)
                if not node:
                    logger.error(f"❌ Node {current_node_id} not found in graph definition.")
                    continue
                
                node_type = getattr(node, "name", node.__class__.__name__)

                # --- C. 事件: Node Started ---
                yield NodeEvent(
                    type=WorkflowEventType.NODE_STARTED,
                    session_id=run_id,
                    node_id=current_node_id,
                    node_type=node_type,
                    input_data="" # 简化日志，具体数据在 Context 中
                )

                # --- D. 执行节点 (Invoke) ---
                # Start 节点特殊处理：传入 input_data
                # 其他节点：传入 None (依赖内部 resolve_inputs 从 context 获取)
                node_input = input_data if current_node_id == self.graph.entry_point else None
                node_config = node.config
                
                try:
                    # [Core] 调用组件逻辑
                    output = await node.invoke(node_input,node_config, context)
                except Exception as e:
                    logger.error(f"❌ Node {current_node_id} execution failed: {e}", exc_info=True)
                    # 可以在这里决定是 Fail-Fast 还是 Fail-Soft
                    raise e 

                # --- E. 更新上下文 ---
                context.set_node_output(current_node_id, output)

                # --- F. 事件: Node Finished ---
                yield NodeFinishedEvent(
                    type=WorkflowEventType.NODE_FINISHED, # [Fix] 必填字段
                    session_id=run_id,
                    node_id=current_node_id,
                    node_type=node_type,
                    output_data=output
                )

                # --- G. 路由与控制流 (Routing) ---
                
                # 1. 信号拦截 (Break/Continue)
                if isinstance(output, dict) and ControlSignal.SIGNAL_KEY in output:
                    signal = output[ControlSignal.SIGNAL_KEY]
                    logger.info(f"🚦 Control Signal received: {signal} at {current_node_id}")
                    # 信号不再向下游传播，直接进入下一次循环(其实是跳过后续入队)，
                    # 等待 Loop 组件捕获此 Event
                    continue

                # 2. 确定下游节点
                outgoing_edges = self.graph.get_outgoing_edges(current_node_id)
                next_nodes = []
                
                # 3. 检查 Active Handle (Branching)
                active_handle = None
                if isinstance(output, dict):
                    active_handle = output.get(ControlSignal.ACTIVE_HANDLE)

                if active_handle:
                    # 分支模式: 只激活匹配的边
                    logger.info(f"🔀 Branching: {current_node_id} -> Handle '{active_handle}'")
                    for edge in outgoing_edges:
                        if edge.source_handle == active_handle:
                            next_nodes.append(edge.target)
                else:
                    # 默认模式: 激活所有默认边 (source_handle is None)
                    for edge in outgoing_edges:
                        if edge.source_handle is None:
                            next_nodes.append(edge.target)

                # 4. 入队
                for nid in next_nodes:
                    # 简单 DAG 去重 (防止菱形结构重复执行)
                    # 复杂循环图需配合 visit count
                    queue.append(nid)

                # --- H. 持久化 (Checkpoint) ---
                # 保存"下一步要做什么"
                status_to_save = "running" if queue else "completed"
                # next_node_to_save = queue[0] if queue else "completed"
                # await self._save_state(run_id, next_node_to_save, context, "running")
                await self._save_state(run_id, queue, context, status_to_save)

            # ==========================================
            # 4. 流程结束
            # ==========================================
            logger.info(f"🏁 Workflow {run_id} Execution Loop Finished.")
            
            # [Fix] 显式保存最终 Completed 状态
            await self._save_state(run_id, [], context, "completed")
            
            # 提取最终输出 (Heuristic: 优先找 End 节点，否则找最后一个)
            final_output = {}
            for nid, out in context.node_outputs.items():
                final_output = out # 简单取最后一个
                # 如果有专门的 End 节点逻辑可在此加强
            
            yield WorkflowCompletedEvent(
                session_id=run_id,
                final_output=final_output
            )

        except Exception as e:
            logger.error(f"💥 Workflow {run_id} Crashed: {e}", exc_info=True)
            yield WorkflowEvent(type=WorkflowEventType.WORKFLOW_ERROR, session_id=run_id, text=str(e))
            # 保存失败状态
            retry_queue = [current_node_id] + queue
            await self._save_state(run_id, retry_queue, context, "failed")
            raise e

    # ==========================================
    # Helpers
    # ==========================================

    async def _save_state(self, run_id: str, execution_queue: List[str], context: WorkflowContext, status: str):
        """持久化状态辅助方法"""
        if self.checkpointer:
            await self.checkpointer.save_checkpoint(WorkflowState(
                run_id=run_id,
                execution_queue=execution_queue,
                context_data=context.node_outputs,
                status=status
            ))

    def _inject_start_data(self, context: WorkflowContext, input_data: Any):
        """将初始输入注入到 'start' 节点的输出中，供后续节点引用 {{ start.key }}"""
        if isinstance(input_data, dict):
            context.set_node_output("start", input_data)
        else:
            context.set_node_output("start", {"input": input_data})

    async def run_to_completion(
        self, 
        inputs: Dict[str, Any], 
        parent_ctx: Optional[WorkflowContext] = None
    ) -> Dict[str, Any]:
        """
        [Sync-like Helper] 运行子图直到结束，并返回结果。
        供 LoopComponent / SubWorkflowComponent 内部调用。
        
        :param inputs: 子图输入
        :param parent_ctx: 父级上下文 (必须传入，否则子图无法访问父级变量)
        """
        # 生成临时 ID
        sub_run_id = f"sub_{uuid.uuid4().hex[:8]}"
        final_res = {}
        
        # 调用 run，传入 parent_ctx
        async for event in self.run(inputs, run_id=sub_run_id, parent_ctx=parent_ctx):
            
            # 1. 捕获最终结果
            if event.type == WorkflowEventType.WORKFLOW_COMPLETED:
                if isinstance(event, WorkflowCompletedEvent):
                    final_res = event.final_output
            
            # 2. 捕获控制信号 (Break/Continue) 并立即向上冒泡
            if event.type == WorkflowEventType.NODE_FINISHED:
                if isinstance(event, NodeFinishedEvent):
                    data = event.output_data
                    if isinstance(data, dict) and ControlSignal.SIGNAL_KEY in data:
                        return data # 立即返回信号字典
        
        return final_res