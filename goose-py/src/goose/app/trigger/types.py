from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"  # Cron
    EVENT = "event"

class TriggerDefinition(BaseModel):
    id: str
    type: TriggerType
    workflow_id: str
    enabled: bool = True
    config: Dict[str, Any] = {}  # Cron表达式, Auth Token等

    # 输入映射：如何将 Trigger 的数据映射为 Workflow 的 Entry Input
    # e.g., {"user_query": "body.query", "request_time": "headers.date"}
    input_mapping: Dict[str, str] = {}

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None