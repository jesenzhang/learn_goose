from enum import Enum
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
import time
import uuid

class SystemEvents(str, Enum):
    # --- 系统级 ---
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_SUSPENDED = "workflow_suspended" # 挂起
    
    # --- 节点级 ---
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    NODE_ERROR = "node_error"
    
    # --- 内容级 (用于 LLM/Tool) ---
    STREAM_TOKEN = "stream_token"      # LLM 吐字
    TOOL_CALL = "tool_call"            # 工具调用
    TOOL_RESULT = "tool_result"        # 工具结果
    CUSTOM = "custom"                  # 用户自定义
    
    # Control
    LOG = "log"

class Event(BaseModel):
    """
    标准事件信封。
    设计原则：扁平化，包含重建时间轴所需的所有元数据。
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    seq_id: int              # 关键：用于前端排序和去重
    type: str
    data: Any                # 业务载荷
    
    # 元数据
    producer_id: Optional[str] = None   # node_id
    parent_run_id: Optional[str] = None # 子工作流追踪
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)