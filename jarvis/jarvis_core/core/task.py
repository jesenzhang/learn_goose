"""
TaskHandle - Handle for managing running tasks.

TaskHandle provides control over running agent executions:
- Cancel tasks
- Check status
- Get results
- Stream events
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncIterator, Callable
from datetime import datetime
import uuid

from .event import Event
from .state import AgentState, AgentStatus


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskHandle:
    """
    Handle for managing a running task.

    TaskHandle is used to:
    1. Track task status
    2. Cancel tasks
    3. Get results
    4. Stream events
    """

    task_id: str
    session_id: str
    run_id: str
    agent_id: str

    # Status tracking
    status: TaskStatus = TaskStatus.PENDING
    start_time: float = field(default_factory=lambda: __import__('time').time())
    end_time: Optional[float] = None

    # Results
    final_state: Optional[AgentState] = None
    final_event: Optional[Event] = None
    error: Optional[str] = None

    # Event queue for streaming
    _event_queue: asyncio.Queue = field(init=False)
    _events: List[Event] = field(default_factory=list, init=False)

    # Cancel flag
    _cancelled: bool = field(default=False, init=False)
    _cancel_event: asyncio.Event = field(init=False)

    def __post_init__(self):
        self._event_queue = asyncio.Queue()
        self._cancel_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self.status == TaskStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """Check if task has completed (successfully or with error)."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def is_cancelled(self) -> bool:
        """Check if task was cancelled."""
        return self.status == TaskStatus.CANCELLED

    @property
    def is_failed(self) -> bool:
        """Check if task failed."""
        return self.status == TaskStatus.FAILED

    def cancel(self) -> None:
        """Cancel the task."""
        self._cancelled = True
        self._cancel_event.set()
        self.status = TaskStatus.CANCELLED
        self.end_time = __import__('time').time()

    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for task to complete.

        Returns:
            True if completed, False if timed out
        """
        try:
            if timeout:
                await asyncio.wait_for(self._cancel_event.wait(), timeout)
            else:
                await self._cancel_event.wait()
            return True
        except asyncio.TimeoutError:
            return False

    async def get_result(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Get the final result of the task.

        Waits for completion if task is still running.
        """
        await self.wait_for_completion(timeout)

        if self.final_state is None:
            return None

        return {
            "state": self.final_state.to_dict(),
            "events": [e.to_dict() if hasattr(e, 'to_dict') else e for e in self._events],
            "error": self.error,
            "duration": (self.end_time or 0) - self.start_time,
        }

    async def stream_events(self) -> AsyncIterator[Event]:
        """
        Stream events as they are produced.

        Yields events in order as they are added to the queue.
        """
        while True:
            # Check if we should stop
            if self.is_completed and self._event_queue.empty():
                break

            # Get next event
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                # No event available, but task might still be running
                if self.is_completed:
                    break
                continue

    def add_event(self, event: Event) -> None:
        """Add an event to the task."""
        self._events.append(event)
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def update_status(self, status: TaskStatus) -> None:
        """Update task status."""
        self.status = status
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.end_time = __import__('time').time()

    def set_final_state(self, state: AgentState) -> None:
        """Set the final state of the task."""
        self.final_state = state

    def set_error(self, error: str) -> None:
        """Set error and mark task as failed."""
        self.error = error
        self.status = TaskStatus.FAILED
        self.end_time = __import__('time').time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskHandle":
        """Create from dictionary."""
        # Handle status enum
        if "status" in data and isinstance(data["status"], str):
            data["status"] = TaskStatus(data["status"])

        return cls(**data)


def create_task_handle(
    session_id: str,
    run_id: str,
    agent_id: str,
) -> TaskHandle:
    """Create a new task handle."""
    return TaskHandle(
        task_id=uuid.uuid4().hex,
        session_id=session_id,
        run_id=run_id,
        agent_id=agent_id,
    )
