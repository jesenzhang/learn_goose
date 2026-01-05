import logging
import asyncio
from typing import Any, Optional, List, Dict

from goose.workflow.graph import Graph
from goose.workflow.context import WorkflowContext
from goose.events import SystemEvents
from goose.workflow.protocol import ControlSignal
from goose.workflow.hook import WorkflowHook

logger = logging.getLogger("goose.workflow.scheduler")

class GraphExecutor:
    """
    [Core] 纯粹的图执行引擎
    职责：
    1. 接收 Graph 和 Context
    2. 拓扑遍历与节点执行
    3. 响应控制信号 (Signal)
    4. 触发钩子 (Hooks)
    
    不负责：数据库读写、HTTP流式管理、用户鉴权
    """
    def __init__(self, hooks: List[WorkflowHook] = None):
        self.hooks = hooks or []

    async def _trigger_hooks(self, method_name: str, *args, **kwargs):
        """批量触发钩子"""
        for hook in self.hooks:
            func = getattr(hook, method_name, None)
            if func:
                try:
                    await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"🪝 Hook error in {method_name}: {e}", exc_info=True)

    async def run(
        self, 
        graph: Graph, 
        inputs: Any, 
        context: WorkflowContext,
        start_node_id: Optional[str] = None, # 支持从指定节点开始 (Resume)
        resume_queue: List[str] = None # 支持恢复执行队列
    ) -> Any:
        """
        核心执行循环。这是一个 Long-Running Coroutine。
        支持 asyncio.CancelledError 进行外部终止。
        """
        run_id = context.session_id
        streamer = context.streamer
        
        # 1. 队列初始化
        queue = resume_queue or []
        if not queue:
            entry_point = start_node_id or graph.entry_point
            if not entry_point: raise ValueError("No entry point found")
            queue.append(entry_point)

        # 2. 触发开始钩子
        await self._trigger_hooks("on_workflow_start", run_id, inputs, context)
        if streamer: await streamer.emit(SystemEvents.WORKFLOW_STARTED, inputs)

        final_output = None
        
        try:
            while queue:
                # [关键] 响应外部的中断信号
                # asyncio.Task.cancel() 会在 await 处抛出 CancelledError
                # 我们利用这一点来实现 Terminate
                
                # [新增] 支持 Suspend 信号
                # 如果 Context 中被标记为挂起，则主动退出
                if context.is_suspended:
                    logger.info(f"⏸️ Workflow {run_id} suspended by signal.")
                    return {"status": "suspended", "queue": queue} # 返回当前状态供上层保存

                current_node_id = queue.pop(0)
                
                # --- 节点执行逻辑 (保持精简) ---
                node = graph.get_node(current_node_id)
                if not node: continue

                # 准备参数
                node_inputs = inputs if current_node_id == graph.entry_point else node.inputs
                node_config = node.config.copy()
                node_config["id"] = current_node_id

                # Hook: Node Start
                await self._trigger_hooks("on_node_start", run_id, node, node_inputs, context)
                if streamer: 
                    await streamer.emit(SystemEvents.NODE_STARTED, {"type": node.type}, producer_id=current_node_id)

                # Execute
                try:
                    output = await node.component.invoke(node_inputs, node_config, context)
                except asyncio.CancelledError:
                    raise # 向上抛出，响应终止
                except Exception as e:
                    # 节点级错误 -> 工作流级错误
                    await streamer.emit(SystemEvents.NODE_ERROR, str(e), producer_id=current_node_id)
                    raise e

                # Update Context
                if output is not None:
                    context.set_node_output(current_node_id, output)
                    final_output = output # 暂定最后一个节点的输出为最终结果

                # Hook: Node End
                await self._trigger_hooks("on_node_end", run_id, node, output, context)
                if streamer:
                    await streamer.emit(SystemEvents.NODE_FINISHED, output, producer_id=current_node_id)

                # --- 拓扑路由 ---
                # 检查特殊控制信号
                if isinstance(output, dict) and output.get(ControlSignal.SIGNAL_KEY) == ControlSignal.SUSPEND:
                     context.is_suspended = True # 下一轮循环处理
                     continue

                # 计算下一跳
                next_nodes = self._calculate_next_nodes(graph, current_node_id, output)
                for nid in next_nodes:
                    if nid not in queue: queue.append(nid)

            # --- 循环结束 (Completed) ---
            logger.info(f"🏁 Workflow {run_id} completed.")
            await self._trigger_hooks("on_workflow_end", run_id, final_output, context)
            if streamer: await streamer.emit(SystemEvents.WORKFLOW_COMPLETED, final_output)
            
            return final_output

        except asyncio.CancelledError:
            logger.info(f"🛑 Workflow {run_id} terminated by user.")
            # 不发 Failed 事件，由 Service 层处理状态
            raise

        except Exception as e:
            logger.error(f"💥 Workflow {run_id} crashed: {e}")
            if streamer: await streamer.emit(SystemEvents.WORKFLOW_FAILED, str(e))
            await self._trigger_hooks("on_workflow_error", run_id, e, context)
            raise

    def _calculate_next_nodes(self, graph: Graph, current_node_id: str, output: Any) -> List[str]:
        """纯逻辑：计算下一跳"""
        outgoing = graph.get_outgoing_edges(current_node_id)
        next_nodes = []
        active_handle = output.get(ControlSignal.ACTIVE_HANDLE) if isinstance(output, dict) else None
        
        for edge in outgoing:
            if active_handle:
                if edge.source_handle == active_handle:
                    next_nodes.append(edge.target)
            elif edge.source_handle is None:
                next_nodes.append(edge.target)
        return next_nodes