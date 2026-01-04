from abc import ABC
from typing import Any, Dict, Optional
from goose.workflow.context import WorkflowContext
from goose.workflow.graph import Node

class WorkflowHook(ABC):
    """
    工作流生命周期钩子基类。
    所有方法都是异步的，且不应阻塞核心流程。
    """

    async def on_workflow_start(self, run_id: str, inputs: Any, context: WorkflowContext):
        """工作流开始前触发"""
        pass

    async def on_node_start(self, run_id: str, node: Node, inputs: Dict[str, Any], context: WorkflowContext):
        """节点开始执行前触发"""
        pass

    async def on_node_end(self, run_id: str, node: Node, output: Any, context: WorkflowContext):
        """节点执行成功后触发 (关键：在此处保存 AI 回复)"""
        pass

    async def on_workflow_end(self, run_id: str, final_output: Any, context: WorkflowContext):
        """工作流结束后触发"""
        pass

    async def on_workflow_error(self, run_id: str, error: Exception, context: WorkflowContext):
        """工作流出错时触发"""
        pass