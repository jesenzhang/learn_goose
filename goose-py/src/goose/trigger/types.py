from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import time

class TriggerType(str, Enum):
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"  # Cron
    EVENT = "event"

class Trigger(BaseModel):
    id: str
    type: TriggerType
    workflow_id: str
    user_id: str       # [必须新增] 记录是谁创建的触发器
    enabled: bool = True
    config: Dict[str, Any] = {}  # Cron表达式, Auth Token等

    # 输入映射：如何将 Trigger 的数据映射为 Workflow 的 Entry Input
    # e.g., {"user_query": "body.query", "request_time": "headers.date"}
    input_mapping: Dict[str, str] = {}

    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
