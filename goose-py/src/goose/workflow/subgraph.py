import uuid
import logging
from typing import Dict, Any, Optional

from .graph import Graph
from .runnable import Runnable
from .context import WorkflowContext
from .nodes import CozeNodeMixin
# 注意：为了避免循环引用，我们可能需要在方法内部导入 Scheduler
# 或者将 Scheduler 抽象为接口，但 Python 中我们可以延迟导入

logger = logging.getLogger("goose.workflow.subgraph")

class SubgraphNode(Runnable, CozeNodeMixin):
    """
    子图节点。
    允许在一个工作流节点中执行另一个完整的工作流。
    """
    def __init__(self, graph: Graph, inputs: Dict[str, Any], name: str = "Subgraph"):
        super().__init__(inputs)
        self.sub_graph = graph
        self.name = name

    async def invoke(self, _: Any, context: WorkflowContext) -> Dict[str, Any]:
        from .scheduler import WorkflowScheduler # 延迟导入避免循环引用

        # 1. 解析输入 (Coze Style)
        # 将父图的数据映射为子图的初始输入
        parent_inputs = self.resolve_inputs(context)
        
        # 2. 生成子图的 run_id (用于持久化隔离)
        # 格式: {父run_id}::{节点ID}_{随机后缀}
        # 随机后缀是为了防止同一个节点在一个父流程中被 Loop 多次调用时 ID 冲突
        sub_run_id = f"{context.session_id}::{self.name}_{uuid.uuid4().hex[:4]}"
        
        logger.info(f"🔄 [Subgraph: {self.name}] Starting sub-workflow run: {sub_run_id}")

        # 3. 初始化子调度器
        # 子调度器会自动使用全局配置的 PersistenceManager
        scheduler = WorkflowScheduler(self.sub_graph)
        
        # 4. 运行子图
        # 我们需要捕获子图的最终输出
        final_output = {}
        
        try:
            # 运行并等待结束
            # input_data 会被自动注入为子图的 start 节点输出
            async for event in scheduler.run(parent_inputs, run_id=sub_run_id):
                if event.type == "workflow_completed":
                    final_output = event.final_output
                elif event.type == "workflow_error":
                    raise RuntimeError(f"Sub-workflow {sub_run_id} failed.")
                
                # 可选：如果需要将子图的事件冒泡给父图，可以在这里处理
                # 但由于 invoke 只能返回结果，事件流通常由 UI 分别监听两个 run_id
        except Exception as e:
            logger.error(f"❌ [Subgraph: {self.name}] Execution failed: {e}")
            raise e

        logger.info(f"✅ [Subgraph: {self.name}] Finished.")
        
        # 5. 返回结果
        # 子图的 final_output 通常是整个 Context 的 node_outputs 字典
        # 我们把它包装一下，或者直接返回
        # 如果父图想访问子图某节点的输出：{{ subgraph_node.inner_node_id.output }}
        # 但为了方便，我们通常约定子图有一个 logical output，这里暂且返回全量
        return final_output