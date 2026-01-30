"""
Event System - The backbone of Jarvis Runtime.

Events are immutable facts that describe everything that happens.
They are single source of truth for the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid
import time


class EventType(str, Enum):
    """Standard event types for the system."""

    # System Level
    RUN_START = "run_start"
    RUN_DONE = "run_done"
    CANCELLED = "cancelled"
    ERROR = "error"

    # LLM Generation
    TOKEN_START = "token_start"
    TOKEN = "token"
    TOKEN_END = "token_end"

    # Thinking (Deep Thought)
    THINKING_START = "thinking_start"
    THINKING_TOKEN = "thinking_token"
    THINKING_END = "thinking_end"

    # Tool Execution
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"

    # Human Interaction
    APPROVAL_REQ = "approval_req"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    # State Changes
    STATE_CHANGE = "state_change"


class SystemEvents(str, Enum):
    """System-level workflow events (from assistant)."""
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_SUSPENDED = "workflow_suspended"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    NODE_ERROR = "node_error"
    STREAM_TOKEN = "stream_token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CUSTOM = "custom"
    LOG = "log"


@dataclass(frozen=True)
class Event:
    """
    Immutable Event - single source of truth.

    Every change in system produces an Event.
    Events are never modified, only appended.

    Key properties:
    - Immutable (frozen=True)
    - Unique ID
    - Causation tracking (causation_id, correlation_id)
    - Timestamp
    """
    # Required fields (no defaults - must come first)
    session_id: str
    agent_id: str
    run_id: str  # For tracking execution runs
    type: str  # Event type (e.g., "token", "tool_start")
    seq_id: int = 0  # Sequence ID for ordering within a run

    # Optional fields with defaults
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    payload: Dict[str, Any] = field(default_factory=dict)
    causation_id: Optional[str] = None  # ID of event that caused this event
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # For grouping related events
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        *,
        session_id: str,
        agent_id: str,
        run_id: str,
        type: str,
        payload: Optional[Dict[str, Any]] = None,
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Event":
        """Factory method to create new events."""
        return cls(
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            type=type,
            payload=payload or {},
            causation_id=causation_id,
            correlation_id=correlation_id or uuid.uuid4().hex,
            metadata=metadata or {},
        )

    def with_seq(self) -> "Event":
        """Create a copy with sequence ID."""
        # Auto-increment seq_id (need to get from store)
        # For now, just return a copy with incremented seq_id
        return Event(
            event_id=self.event_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            run_id=self.run_id,
            type=self.type,
            payload=self.payload,
            causation_id=self.causation_id,
            correlation_id=self.correlation_id,
            timestamp=self.timestamp,
            metadata=self.metadata,
            seq_id=self.seq_id + 1,
        )


def create_run_start_event(
    session_id: str,
    agent_id: str,
    run_id: str,
) -> Event:
    """Create a run start event."""
    return Event.new(
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        type=EventType.RUN_START,
        payload={"run_id": run_id},
    )


def create_token_event(
    session_id: str,
    agent_id: str,
    run_id: str,
    token: str,
) -> Event:
    """Create a token event."""
    return Event.new(
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        type=EventType.TOKEN,
        payload={"token": token},
    )


def create_tool_start_event(
    session_id: str,
    agent_id: str,
    run_id: str,
    tool_name: str,
    tool_args: Dict[str, Any],
) -> Event:
    """Create a tool start event."""
    return Event.new(
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        type=EventType.TOOL_START,
        payload={
            "tool_name": tool_name,
            "tool_args": tool_args,
        },
    )


def create_tool_end_event(
    session_id: str,
    agent_id: str,
    run_id: str,
    tool_name: str,
    result: Any,
    is_error: bool = False,
) -> Event:
    """Create a tool end event."""
    return Event.new(
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        type=EventType.TOOL_END,
        payload={
            "tool_name": tool_name,
            "result": result,
            "is_error": is_error,
        },
    )


def create_error_event(
    session_id: str,
    agent_id: str,
    run_id: str,
    error: str,
    error_type: str = "Exception",
) -> Event:
    """Create an error event."""
    return Event.new(
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        type=EventType.ERROR,
        payload={
            "error": error,
            "error_type": error_type,
        },
    )


def create_state_change_event(
    session_id: str,
    agent_id: str,
    run_id: str,
    state: str,
    message: str,
) -> Event:
    """Create a state change event."""
    return Event.new(
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        type=EventType.STATE_CHANGE,
        payload={
            "state": state,
            "message": message,
        },
    )
