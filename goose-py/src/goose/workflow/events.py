from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import time

class WorkflowEventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_ERROR = "workflow_error"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    NODE_ERROR = "node_error"

class Event(BaseModel):
    """基础事件类"""
    type: WorkflowEventType
    timestamp: float = Field(default_factory=lambda: __import__("time").time())
    
class WorkflowEvent(Event):
    """工作流级事件"""
    session_id: str
    # 允许 output 是任意类型 (dict, str, list)
    final_output: Optional[Any] = None 
    text: Optional[str] = None

class NodeEvent(WorkflowEvent):
    """节点级事件"""
    node_id: str
    node_type: str
    input_data: Optional[Any] = None

class NodeFinishedEvent(NodeEvent):
    """
    [关键修复] output_data 必须是 Any，因为节点可能返回 Dict/List/PydanticModel
    """
    type: WorkflowEventType = WorkflowEventType.NODE_FINISHED
    output_data: Any
    
class WorkflowCompletedEvent(WorkflowEvent):
    type: WorkflowEventType = WorkflowEventType.WORKFLOW_COMPLETED
    final_output: Any