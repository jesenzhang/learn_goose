from pydantic import BaseModel, Field
from typing import Dict, Any
from goose.command.bus import Command

# 定义命令，并指定返回值类型是 str (Run ID)
class RunWorkflowCommand(BaseModel, Command[str]):
    workflow_id: str
    user_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    source: str = "trigger" # 审计用