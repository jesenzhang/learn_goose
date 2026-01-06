import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

# 1. 定义状态枚举 (强类型控制)
class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# 2. 定义核心模型
class Execution(BaseModel):
    """
    对应表: executions
    """
    # ID: 通常由 Python 生成，确保在入库前就已经有 ID
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    
    # 关联信息
    workflow_id: str
    title: str = ""  # 快照标题，允许为空
    
    # 状态: 映射到 SQL 的 TEXT，Repository 会自动处理 Enum -> str
    status: ExecutionStatus = ExecutionStatus.PENDING
    
    # 数据载荷: 映射到 SQL 的 TEXT (JSON)
    # Repository 的 _to_db_params 会自动检测 dict 并 dumps 为 json 字符串
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Optional[Dict[str, Any]] = None  # 初始为空
    
    # 结果与统计
    error: Optional[str] = None
    duration: Optional[float] = None  # 耗时，任务结束前为空
    
    # 时间戳: 映射到 SQL 的 REAL
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # --- 辅助方法 (Optional) ---
    @property
    def is_finished(self) -> bool:
        return self.status in (
            ExecutionStatus.COMPLETED, 
            ExecutionStatus.FAILED, 
            ExecutionStatus.CANCELLED
        )