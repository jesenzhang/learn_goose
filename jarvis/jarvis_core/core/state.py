"""
State Management for Agents.

AgentState represents the current state of an agent.
It's a pure data structure - no methods, no logic.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime


class AgentStatus(str, Enum):
    """Agent execution status."""

    # Lifecycle states
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    # Skill states
    SKILL_ACTIVE = "skill_active"

    # Wait states
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"


@dataclass
class AgentState:
    """
    Pure state object for agents.

    Agent logic never mutates this directly.
    Instead, it creates new AgentState instances.

    This enables:
    - Event sourcing (state = f(events))
    - Time travel (state at any point)
    - Testing (deterministic state transitions)
    """

    # Identity
    agent_id: str
    session_id: str
    run_id: str

    # Status
    status: AgentStatus = AgentStatus.IDLE

    # Execution state
    current_step: int = 0
    total_steps: int = 0

    # Skill state
    active_skill: Optional[str] = None
    skill_state: Dict[str, Any] = field(default_factory=dict)

    # Thinking/state data
    context: Dict[str, Any] = field(default_factory=dict)
    working_memory: Dict[str, Any] = field(default_factory=dict)

    # Execution metadata
    created_at: float = field(default_factory=lambda: __import__('time').time())
    updated_at: float = field(default_factory=lambda: __import__('time').time())

    # Error state
    last_error: Optional[str] = None
    error_count: int = 0

    # Conversation state
    messages: List[Dict[str, Any]] = field(default_factory=list)
    conversation_summary: Optional[str] = None

    # Metrics
    tokens_generated: int = 0
    tools_executed: int = 0
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "active_skill": self.active_skill,
            "skill_state": self.skill_state,
            "context": self.context,
            "working_memory": self.working_memory,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_error": self.last_error,
            "error_count": self.error_count,
            "messages": self.messages,
            "conversation_summary": self.conversation_summary,
            "tokens_generated": self.tokens_generated,
            "tools_executed": self.tools_executed,
            "execution_time": self.execution_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        """Create from dictionary."""
        # Handle status enum
        if "status" in data and isinstance(data["status"], str):
            data["status"] = AgentStatus(data["status"])

        return cls(**data)


@dataclass
class Snapshot:
    """
    A snapshot of agent state at a specific point.

    Snapshots enable:
    - Fast state recovery
    - Time travel
    - Checkpoint/restore
    """

    snapshot_id: str
    state: AgentState
    seq_id: int
    created_at: float = field(default_factory=lambda: __import__('time').time())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "state": self.state.to_dict(),
            "seq_id": self.seq_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Snapshot":
        """Create from dictionary."""
        # Convert state dict back to AgentState
        if "state" in data and isinstance(data["state"], dict):
            data["state"] = AgentState.from_dict(data["state"])
        return cls(**data)


def create_initial_state(
    agent_id: str,
    session_id: str,
    run_id: str,
    context: Optional[Dict[str, Any]] = None,
) -> AgentState:
    """Create an initial agent state."""
    return AgentState(
        agent_id=agent_id,
        session_id=session_id,
        run_id=run_id,
        status=AgentStatus.IDLE,
        context=context or {},
    )
