import asyncio
from enum import Enum
from typing import Any, AsyncGenerator, Optional,Union
from goose.events.streamer import BaseStreamer
from goose.workflow.events import WorkflowEventType


class WorkflowStreamer(BaseStreamer):
    """
    [业务层] 工作流专用的流管理器。
    可以添加特定于 Workflow 的 Helper 方法。
    """
    async def log(self, message: str):
        await self.emit("log", message)
        
    async def emit_node_start(self, node_id: str, node_type: str, inputs: dict):
        """便捷方法：发送节点开始事件"""
        await self.emit(
            WorkflowEventType.NODE_STARTED, 
            data=inputs, 
            node_id=node_id, 
            node_type=node_type
        )
