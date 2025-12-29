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

logger = logging.getLogger("goose.workflow.scheduler")

# class WorkflowScheduler:
#     """
#     [增强版] 工作流调度器。
#     支持控制流协议 (If/Else, Loop, Break) 和多路并行执行。
#     """
#     def __init__(self, graph: Graph, checkpointer: Optional[WorkflowCheckpointer] = None):
#         self.graph = graph
#         register_workflow_schemas()
#         self.checkpointer = checkpointer or WorkflowRepository()

#     async def run(
#         self, 
#         input_data: Any, 
#         run_id: str = None, 
#         resume: bool = False,
#         parent_ctx: WorkflowContext = None # [新增] 支持子图继承 Context
#     ) -> AsyncGenerator[WorkflowEvent, None]:
        
#         # --- 1. 身份与上下文初始化 (保持原有逻辑，略有增强) ---
#         should_inject_start = False
        
#         if not run_id:
#             session = await SessionManager.create_workflow_session(name="Auto Workflow Run")
#             run_id = session.id
#             should_inject_start = True
#             logger.info(f"🆕 Auto-created Workflow Session: {run_id}")
#         else:
#             try:
#                 await SessionManager.get_session(run_id)
#                 if resume:
#                     logger.info(f"🔄 Resuming session {run_id}")
#                     should_inject_start = False
#                 else:
#                     logger.info(f"🔄 Restarting session {run_id}")
#                     should_inject_start = True
#             except ValueError:
#                 # 显式创建子图 Session
#                 await SessionManager.create_session(
#                     session_id=run_id, 
#                     name=f"Sub-Workflow {run_id[-6:]}", 
#                     session_type=SessionType.WORKFLOW
#                 )
#                 should_inject_start = True

#         context = WorkflowContext(session_id=run_id)
#         # [新增] 继承父级变量 (对于 Loop/SubWorkflow 很重要)
#         if parent_ctx:
#             context.variables.update(parent_ctx.variables)

#         # --- 2. 状态恢复 ---
#         queue = [] # 执行队列 (FIFO)
        
#         if resume and self.checkpointer:
#             state = await self.checkpointer.load_checkpoint(run_id)
#             if state and state.status != "completed":
#                 context.node_outputs = state.context_data
#                 # 恢复执行点
#                 if state.current_node_id and state.current_node_id != "completed":
#                     # 注意：简单恢复只支持单个执行点，复杂并行恢复需要存储 Queue 状态
#                     queue.append(state.current_node_id)
#                 should_inject_start = False
#             else:
#                 should_inject_start = True # 状态无效，重新开始

#         # 注入初始数据
#         if should_inject_start:
#             # 如果存在显式的 Start 节点，数据会在执行时传入；否则注入到 outputs
#             # 为了兼容旧逻辑，我们依然做一次注入，或者依赖 ComponentNode.invoke 的 fallback
#             self._inject_start_data(context, input_data)
            
#             if self.graph.entry_point:
#                 queue.append(self.graph.entry_point)

#         if not queue:
#             # 如果没找到入口且没恢复状态
#             if self.graph.entry_point:
#                 queue.append(self.graph.entry_point)
#             else:
#                 logger.warning("No entry point found. Workflow might be empty.")

#         yield WorkflowEvent(type=WorkflowEventType.WORKFLOW_STARTED, session_id=run_id)

#         try:
#             # --- 3. 执行循环 (BFS + Control Protocol) ---
#             while queue:
#                 # 取出当前要执行的节点
#                 current_node_id = queue.pop(0)
                
#                 # A. 挂起检查
#                 if current_node_id == "__SUSPEND__":
#                     await self._save_state(run_id, current_node_id, context, "suspended")
#                     return

#                 # B. 获取节点
#                 node = self.graph.get_node(current_node_id)
#                 if not node:
#                     logger.warning(f"Node {current_node_id} not found, skipping.")
#                     continue
                
#                 node_type = getattr(node, "name", node.__class__.__name__)

#                 # C. 事件：节点开始
#                 yield NodeEvent(
#                     type=WorkflowEventType.NODE_STARTED,
#                     session_id=run_id,
#                     node_id=current_node_id,
#                     node_type=node_type,
#                     input_data="" # 简化日志
#                 )

#                 # D. 执行节点
#                 # 传入 input_data 仅针对 Start 节点 (作为 Entry Point 时)
#                 # 其他节点通过 context 获取数据
#                 node_input = input_data if current_node_id == self.graph.entry_point else None
                
#                 try:
#                     output = await node.invoke(node_input, context)
#                 except Exception as e:
#                     logger.error(f"❌ Node {current_node_id} failed: {e}")
#                     raise e # 或者 Fail-Soft

#                 # E. 保存输出
#                 context.set_node_output(current_node_id, output)

#                 # F. 事件：节点结束
#                 yield NodeFinishedEvent(
#                     session_id=run_id,
#                     node_id=current_node_id,
#                     node_type=node_type,
#                     output_data=output
#                 )

#                 # --- G. 路由决策 (Control Protocol) ---
                
#                 # 1. 检查中断信号 (Break/Continue)
#                 if ControlSignal.SIGNAL_KEY in output:
#                     # 信号不再向下传递，而是直接由 Loop 组件捕获
#                     # 我们停止调度该分支的后续节点
#                     logger.info(f"🛑 Signal '{output[ControlSignal.SIGNAL_KEY]}' at {current_node_id}")
#                     continue

#                 # 2. 获取出边
#                 outgoing_edges = self.graph.get_outgoing_edges(current_node_id)
#                 next_nodes = []

#                 # 3. 检查激活句柄 (If-Else)
#                 active_handle = output.get(ControlSignal.ACTIVE_HANDLE)
                
#                 if active_handle:
#                     # 分支模式：只走匹配的边
#                     logger.info(f"🔀 Branching: {current_node_id} -> '{active_handle}'")
#                     for edge in outgoing_edges:
#                         if edge.source_handle == active_handle:
#                             next_nodes.append(edge.target)
#                 else:
#                     # 普通模式：走所有默认边 (source_handle is None)
#                     # (或者兼容旧逻辑：如果不传 handle，则所有边都走)
#                     for edge in outgoing_edges:
#                         if edge.source_handle is None:
#                             next_nodes.append(edge.target)

#                 # 4. 加入队列
#                 for nid in next_nodes:
#                     # 简单去重，防止菱形结构重复执行 (对于 DAG)
#                     # 如果需要支持循环图，则不能简单去重，需引入 visit count
#                     queue.append(nid)

#                 # H. 持久化 (Checkpoint)
#                 # 保存的是队列中下一个要执行的节点 (简化版)
#                 next_checkpoint_id = queue[0] if queue else "completed"
#                 await self._save_state(run_id, next_checkpoint_id, context, "running")

#             # --- Loop End ---
#             logger.info(f"🏁 Workflow {run_id} Completed.")
#             # [修复] 循环结束后，显式保存一次 Completed 状态
#             # 否则数据库里最后一条记录的状态永远是 "running"
#             if self.checkpointer:
#                 await self.checkpointer.save_checkpoint(WorkflowState(
#                     run_id=run_id,
#                     current_node_id="completed", # 或者 self.graph.finish_point
#                     context_data=context.node_outputs,
#                     status="completed" # <--- 关键：标记为完成
#                 ))
                
#             # 尝试获取最终输出 (优先取 End 节点，否则取最后一个)
#             final_output = {}
#             for nid, out in context.node_outputs.items():
#                 # 简单策略：如果节点名包含 'end'，或是最后一个执行的
#                 final_output = out 
            
#             yield WorkflowCompletedEvent(
#                 session_id=run_id,
#                 final_output=final_output
#             )

#         except Exception as e:
#             logger.error(f"❌ Workflow {run_id} Error: {e}", exc_info=True)
#             yield WorkflowEvent(type=WorkflowEventType.WORKFLOW_ERROR, session_id=run_id, text=str(e))
#             await self._save_state(run_id, current_node_id, context, "failed")
#             raise e

#     async def _save_state(self, run_id, node_id, context, status):
#         """Helper: 保存状态"""
#         if self.checkpointer:
#             await self.checkpointer.save_checkpoint(WorkflowState(
#                 run_id=run_id,
#                 current_node_id=node_id,
#                 context_data=context.node_outputs,
#                 status=status
#             ))

#     def _inject_start_data(self, context: WorkflowContext, input_data: Any):
#         """兼容旧逻辑：注入 Start 数据"""
#         if isinstance(input_data, dict):
#             context.set_node_output("start", input_data)
#         else:
#             context.set_node_output("start", {"input": input_data})

#     async def run_to_completion(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
#         """
#         [Helper] 运行直到结束，返回结果。
#         供 Loop/SubWorkflow 组件内部调用。
#         """
#         # 自动生成临时 ID
#         import uuid
#         run_id = f"sub_{uuid.uuid4().hex[:8]}"
        
#         final_res = {}
#         # 这里的 parent_ctx 需要从外部传入，或者是当前的 context
#         # 由于这个方法是在 Component.execute 内部调用的，
#         # 我们可能需要稍微调整接口，让 run_to_completion 接收 parent_ctx
        
#         async for event in self.run(inputs, run_id=run_id):
#             if event.type == WorkflowEventType.WORKFLOW_COMPLETED:
#                 if isinstance(event, WorkflowCompletedEvent):
#                     final_res = event.final_output
            
#             # 捕获信号并立即返回
#             if event.type == WorkflowEventType.NODE_FINISHED:
#                 if isinstance(event, NodeFinishedEvent):
#                     # event.output_data 可能是 dict 或其他
#                     data = event.output_data
#                     if isinstance(data, dict) and ControlSignal.SIGNAL_KEY in data:
#                         return data
        
#         return final_res
    
    

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
        parent_ctx: WorkflowContext = None 
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """
        执行工作流。
        :param input_data: 初始输入数据
        :param run_id: 会话 ID (Session ID)
        :param resume: 是否从断点恢复
        :param parent_ctx: 父级上下文 (用于子工作流变量继承)
        """
        
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

        # 创建上下文
        context = WorkflowContext(session_id=run_id)
        
        # [Feature] 变量继承: 将父级上下文变量复制到当前上下文
        if parent_ctx:
            context.variables.update(parent_ctx.variables)

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

        # 注入初始数据 (无论是 Start 节点还是隐式输入)
        if should_inject_start:
            self._inject_start_data(context, input_data)

        # 发送开始事件
        yield WorkflowEvent(type=WorkflowEventType.WORKFLOW_STARTED, session_id=run_id)

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
                
                try:
                    # [Core] 调用组件逻辑
                    output = await node.invoke(node_input, context)
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