import json
from typing import Protocol, Optional, Dict, Any,List
from pydantic import BaseModel,Field
from datetime import datetime
from goose.persistence import BaseRepository,with_table,TableSpec
import logging

logger = logging.getLogger(__name__)

class WorkflowCheckpoint(BaseModel):
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
    async def save_checkpoint(self, state: WorkflowCheckpoint) -> None:
        ...

    async def load_checkpoint(self, run_id: str) -> Optional[WorkflowCheckpoint]:
        ...
        
WORKFLOW_CHECKPOINT_SCHEMA =  """
    CREATE TABLE IF NOT EXISTS workflow_checkpoints (
        run_id TEXT PRIMARY KEY,
        execution_queue TEXT,   -- [变更] 存储 JSON List ["node_a", "node_b"]
        context_data TEXT,      -- JSON: 存储 node_outputs
        status TEXT,            -- running, suspended, completed, failed
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    
@with_table(name='workflow_checkpoints',model=WorkflowCheckpoint,sql=WORKFLOW_CHECKPOINT_SCHEMA,priority=0,pk='run_id',attr_name='checkpoint_spec')
class WorkflowCheckpointRepository(BaseRepository,WorkflowCheckpointer):
    """WorkflowCheckpointRepository"""

    async def save_checkpoint(self, state: WorkflowCheckpoint):
        """保存状态"""
        try:
            await self._upsert(WorkflowCheckpoint,state)
        except Exception as e:
            logger.error(f"❌ FATAL ERROR: Database Save Failed! Reason: {e}")
            raise e
        
    async def load_checkpoint(self, run_id: str) -> Optional[WorkflowCheckpoint]:
        """加载状态"""
        try:
            data = await self._get(WorkflowCheckpoint,run_id)
            return data
        except Exception as e:
            logger.error(f"❌ FATAL ERROR: Database Load Failed! Reason: {e}")
            raise e
    