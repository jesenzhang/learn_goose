import json
from typing import Protocol, Optional, Dict, Any,List
from pydantic import BaseModel,Field
from datetime import datetime

class WorkflowState(BaseModel):
    """
    [DTO] 工作流状态快照。
    用于在 Scheduler 和 Repository 之间传输数据。
    """
    run_id: str
    
    # [Upgrade] 支持并行恢复：存储待执行的节点列表

    execution_queue: List[str] = Field(default_factory=list)
    
    # 上下文数据 (Node Outputs + Variables)
    context_data: Dict[str, Any] = Field(default_factory=dict)
    
    # 状态元数据
    status: str = "pending" # pending, running, suspended, completed, failed
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    # --- 兼容性属性 (可选) ---
    @property
    def current_node_id(self) -> Optional[str]:
        """兼容旧代码：返回队列中的第一个节点"""
        return self.execution_queue[0] if self.execution_queue else None

class WorkflowCheckpointer(Protocol):
    """
    Checkpointer 只是一个行为契约：保存和加载状态。
    它不关心 Session 是怎么创建的。
    """
    async def save_checkpoint(self, state: WorkflowState) -> None:
        ...

    async def load_checkpoint(self, run_id: str) -> Optional[WorkflowState]:
        ...
        
