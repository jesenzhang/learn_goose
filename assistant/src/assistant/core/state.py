"""
State Management Module - Agent state persistence and database operations.

This module handles:
- Agent state model with Pydantic validation
- SQLite database operations with proper transaction handling
- Connection pooling for better performance
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"  # 任务已取消
    ERROR = "error"


class AgentState(BaseModel):
    """
    Agent state model.

    Attributes:
        session_id: Unique session identifier
        user_id: Optional user identifier for multi-user support
        status: Current agent status
        history: Conversation history with LLM
        current_intent: Currently active skill/intent
        current_plan: Execution plan steps
        pending_tool_call: Tool awaiting human approval
        title: Session title for UI display
        shared_memory: Key-value storage for artifacts and cross-turn data
        run_config: user provided run configuration for the turn
        updated_at: Last activity timestamp
        last_active: Human-readable last activity time
    """
    session_id: int
    current_run_id: Optional[str] = Field(default=None, description="Current run identifier")
    user_id: Optional[int] = Field(default=None, description="User identifier for multi-user support")
    status: AgentStatus = AgentStatus.IDLE
    history: List[Dict] = Field(default_factory=list, exclude=True)
    active_skill: Optional[str] = Field(default=None, description="Current activated skill context")
    intent_session: Dict[str, Any] = Field(default_factory=dict, description="Internal state for Intent Recognizer")
    current_plan: List[str] = []
    pending_tool_call: Optional[Dict] = None
    intent_queue: List[Dict] = Field(default_factory=list) # 存储待执行的意图列表
    title: str = "New Chat"
    # 当前回合的结构化信息（工具调用、响应等），最终添加到回复消息的 metadata 中
    turn_structured_info: Dict[str, Any] = Field(default_factory=dict)
    shared_memory: Dict[str, Any] = Field(default_factory=dict)
    run_config: Dict[str, Any] = Field(default_factory=dict, exclude=True)
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "AgentState":
        """Deserialize from JSON."""
        return cls.model_validate_json(json_str)

