"""Task scheduling for V2, extracted from legacy agent logic."""

import asyncio
import logging
import time
from typing import Dict, Optional

from .agent_core import TaskHandle as LegacyTaskHandle
from ..state import AgentState
from ..events.legacy import EventType


class TaskRunner:
    """Owns task lifecycle and scheduling."""

    def __init__(self, agent):
        self._agent = agent
        self._logger = logging.getLogger(__name__)
        # Share the same dict with legacy agent to keep internal lookups consistent.
        if hasattr(agent, "_running_tasks") and isinstance(agent._running_tasks, dict):
            self._running_tasks = agent._running_tasks
        else:
            self._running_tasks = {}
            agent._running_tasks = self._running_tasks

    def get_task_handle(self, session_id: int) -> Optional[LegacyTaskHandle]:
        return self._running_tasks.get(session_id)

    async def cancel_running_task(self, session_id: int) -> bool:
        handle = self._running_tasks.get(session_id)
        if handle and handle.is_running:
            handle.task.cancel()
            del self._running_tasks[session_id]
            return True
        return False

    async def run_task(
        self,
        state: AgentState,
        run_id: str,
        input_data: Dict | str = None,
        resume: bool = False,
        approval_data: Dict = None,
        user_id: Optional[int] = None,
    ) -> LegacyTaskHandle:
        """Schedule a new task or return the running one."""
        start_signal = asyncio.Event()
        if user_id is None:
            user_id = state.user_id
        current_run_id = run_id

        # 2) If there's a running task, return it.
        handle = self.get_task_handle(state.session_id)
        if handle and handle.is_running:
            return handle

        # Record run state for reconnect/resume safety.
        state.active_run_id = current_run_id
        state.last_run_id = current_run_id
        if not resume:
            state.pending_run_id = None
        if hasattr(self._agent, "_schedule_state_save"):
            self._agent._schedule_state_save(state.session_id, state)

        # 3) Start task wrapper (non-blocking).
        task = asyncio.create_task(
            self._task_wrapper(
                session_id=state.session_id,
                task_id=current_run_id,
                input_data=input_data,
                resume=resume,
                approval_data=approval_data,
                user_id=user_id,
                start_signal=start_signal,
                state=state,
            )
        )

        handle = LegacyTaskHandle(task, time.time(), current_run_id, start_signal, input_data)
        self._running_tasks[state.session_id] = handle
        return handle

    async def _task_wrapper(
        self,
        session_id: int,
        task_id: str,
        input_data: Dict | str = None,
        resume: bool = False,
        approval_data: Dict = None,
        user_id: Optional[int] = None,
        start_signal: asyncio.Event = None,
        state: Optional[AgentState] = None,
    ):
        try:
            await self._agent._emit_event(
                EventType.RUN_START,
                {"session_id": session_id, "run_id": task_id},
                session_id=session_id,
                run_id=task_id,
                user_id=user_id,
            )

            try:
                await self._agent._run_task_body(
                    session_id,
                    task_id,
                    input_data,
                    resume,
                    approval_data,
                    user_id,
                    start_signal,
                    state,
                )
            except asyncio.CancelledError:
                self._logger.info(f"Task for session {session_id} was cancelled.")
                await self._agent._emit_event(
                    EventType.CANCELLED,
                    {"msg": "Task cancelled"},
                    session_id=session_id,
                    run_id=task_id,
                    user_id=user_id,
                )
                raise
            except Exception as e:
                self._logger.error(
                    f"Task execution failed for session {session_id}: {e}",
                    exc_info=True,
                )
                await self._agent._emit_event(
                    EventType.ERROR,
                    {"error": str(e), "type": type(e).__name__},
                    session_id=session_id,
                    run_id=task_id,
                    user_id=user_id,
                )
        finally:
            await self._agent._emit_event(
                EventType.DONE,
                {"session_id": session_id, "run_id": task_id},
                session_id=session_id,
                run_id=task_id,
                user_id=user_id,
            )
            if state is not None:
                state.active_run_id = None
                state.last_run_id = task_id
                if hasattr(self._agent, "_schedule_state_save"):
                    self._agent._schedule_state_save(session_id, state)
            self._running_tasks.pop(session_id, None)
