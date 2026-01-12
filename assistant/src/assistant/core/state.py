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
        updated_at: Last activity timestamp
        last_active: Human-readable last activity time
    """
    session_id: str
    user_id: Optional[str] = Field(default=None, description="User identifier for multi-user support")
    status: AgentStatus = AgentStatus.IDLE
    history: List[Dict] = []
    active_skill: Optional[str] = Field(default=None, description="Current activated skill context")
    intent_session: Dict[str, Any] = Field(default_factory=dict, description="Internal state for Intent Recognizer")
    current_plan: List[str] = []
    pending_tool_call: Optional[Dict] = None
    title: str = "New Chat"
    shared_memory: Dict[str, Any] = {}
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_json(self) -> str:
        """Serialize to JSON."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "AgentState":
        """Deserialize from JSON."""
        return cls.model_validate_json(json_str)

