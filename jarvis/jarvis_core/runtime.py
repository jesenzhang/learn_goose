"""
Runtime - Core execution engine for Jarvis.

The Runtime is responsible for:
1. Event loop and state management
2. Effect execution coordination
3. Snapshot management
4. Event sourcing and replay
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, AsyncIterator
import uuid

from jarvis_core.core.agent import Agent
from jarvis_core.core.event import Event, EventType
from jarvis_core.core.state import AgentState
from jarvis_core.core.task import TaskHandle, TaskStatus
from jarvis_core.core.effect import Effect, EffectType

from jarvis_core.store.event_store import EventStore
from jarvis_core.store.state_store import StateStore
from jarvis_core.store.snapshot import SnapshotManager

from jarvis_core.executor.base import EffectExecutor, RealExecutor


logger = logging.getLogger(__name__)


@dataclass
class RuntimeConfig:
    """Configuration for Runtime."""

    # Storage
    event_store: EventStore
    state_store: StateStore

    # Execution
    executor: EffectExecutor

    # Snapshot management
    snapshot_manager: Optional[SnapshotManager] = None

    # Event handlers
    event_handlers: Dict[str, List[Callable]] = field(default_factory=dict)

    # Concurrency
    max_concurrent_effects: int = 10


class Runtime:
    """
    Core execution engine.

    The Runtime orchestrates:
    1. Event processing
    2. Agent state transitions
    3. Effect execution
    4. Snapshot management
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config

        # Active tasks
        self._tasks: Dict[str, TaskHandle] = {}
        self._task_lock = asyncio.Lock()

    async def run(
        self,
        agent: Agent,
        session_id: str,
        input_event: Event,
        run_id: Optional[str] = None,
    ) -> TaskHandle:
        """
        Run an agent with an input event.

        Creates a new task and starts processing.
        Returns a TaskHandle for control and monitoring.
        """
        # Generate run_id if not provided
        if run_id is None:
            run_id = uuid.uuid4().hex

        # Create task handle
        task = TaskHandle(
            task_id=uuid.uuid4().hex,
            session_id=session_id,
            run_id=run_id,
            agent_id=agent.id,
        )

        # Track task
        async with self._task_lock:
            self._tasks[task.task_id] = task

        # Start processing in background
        asyncio.create_task(
            self._process_task(agent, task, input_event)
        )

        return task

    async def _process_task(
        self,
        agent: Agent,
        task: TaskHandle,
        input_event: Event,
    ) -> None:
        """
        Process a task until completion or cancellation.

        This is the main event loop for a single task.
        """
        try:
            # Update status
            task.update_status(TaskStatus.RUNNING)

            # Initialize or load state
            state = await self._initialize_state(agent, task.session_id, task.run_id)

            # Process input event
            await self._process_event(agent, state, input_event, task)

            # Run event loop
            while task.is_running and not task._cancelled:
                # Check for more events to process
                if task._event_queue.empty():
                    # No more events, task is complete
                    task.update_status(TaskStatus.COMPLETED)
                    task.set_final_state(state)
                    break

                # Get next event
                event = await asyncio.wait_for(
                    task._event_queue.get(),
                    timeout=0.1,
                )

                # Process event
                await self._process_event(agent, state, event, task)

        except asyncio.CancelledError:
            task.update_status(TaskStatus.CANCELLED)
            logger.info(f"Task {task.task_id} was cancelled")

        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            task.update_status(TaskStatus.FAILED)
            task.set_error(str(e))

        finally:
            # Clean up task
            async with self._task_lock:
                if task.task_id in self._tasks:
                    del self._tasks[task.task_id]

    async def _initialize_state(
        self,
        agent: Agent,
        session_id: str,
        run_id: str,
    ) -> AgentState:
        """Initialize or load agent state."""
        # Try to load from state store
        state = await self.config.state_store.load_state(session_id, run_id)

        if state is None:
            # Create new initial state
            state = agent.initialize(session_id, run_id)
            await self.config.state_store.save_state(session_id, run_id, state)

        return state

    async def _process_event(
        self,
        agent: Agent,
        state: AgentState,
        event: Event,
        task: TaskHandle,
    ) -> None:
        """
        Process a single event through the agent.

        Flow:
        1. Agent.reduce(event) -> new_state + effects
        2. Execute effects -> new events
        3. Update state
        4. Store event
        5. Save state if needed
        """
        # Emit event
        await self._emit_event(event)

        # Add to task event stream
        task.add_event(event)

        # Agent reduction
        new_state, effects = agent.reduce(state, event)

        # Execute effects
        for effect in effects:
            if task._cancelled:
                break

            # Check snapshot manager
            if self.config.snapshot_manager:
                self.config.snapshot_manager.record_event()

                if await self.config.snapshot_manager.should_snapshot(
                    task.session_id,
                    task.run_id,
                ):
                    await self._create_snapshot(new_state, task)

            # Handle state save effect specially
            if effect.effect_type == EffectType.SAVE_STATE:
                await self._handle_save_state(effect, task)
                continue

            # Execute effect
            result_event = await self.config.executor.execute(
                effect,
                task.session_id,
                task.agent_id,
                task.run_id,
            )

            # Emit result event
            await self._emit_event(result_event)

            # Add to task event stream
            task.add_event(result_event)

            # Feed result event back into agent
            if result_event.type in ("tool_end", "assistant_response", "error"):
                await self._process_event(agent, new_state, result_event, task)

        # Update state
        state = new_state

        # Save state to store
        await self.config.state_store.save_state(
            task.session_id,
            task.run_id,
            state,
        )

    async def _handle_save_state(
        self,
        effect: Effect,
        task: TaskHandle,
    ) -> None:
        """Handle save state effect."""
        state_dict = effect.payload.get("state")
        if state_dict:
            from jarvis_core.core.state import AgentState
            state = AgentState.from_dict(state_dict)
            await self.config.state_store.save_state(
                task.session_id,
                task.run_id,
                state,
            )

    async def _create_snapshot(
        self,
        state: AgentState,
        task: TaskHandle,
    ) -> None:
        """Create a snapshot."""
        if not self.config.snapshot_manager:
            return

        # Get current event count
        events = await self.config.event_store.get_events(
            task.session_id,
            task.run_id,
        )

        # Create snapshot
        snapshot = await self.config.snapshot_manager.create_snapshot(
            state=state,
            seq_id=len(events),
            metadata={"task_id": task.task_id},
        )

        logger.debug(
            f"Created snapshot {snapshot.snapshot_id} "
            f"for run {task.run_id}"
        )

    async def _emit_event(self, event: Event) -> None:
        """Emit an event to handlers."""
        handlers = self.config.event_handlers.get(event.type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    def register_event_handler(
        self,
        event_type: str,
        handler: Callable,
    ) -> None:
        """Register a handler for a specific event type."""
        if event_type not in self.config.event_handlers:
            self.config.event_handlers[event_type] = []
        self.config.event_handlers[event_type].append(handler)

    async def replay(
        self,
        session_id: str,
        run_id: str,
        from_seq_id: int = 0,
        mode: str = "execute",
    ) -> List[Event]:
        """
        Replay events for a run.

        Args:
            session_id: Session to replay
            run_id: Run to replay
            from_seq_id: Starting sequence ID
            mode: "execute" to run effects, "dry_run" to only only replay

        Returns:
            List of events from replay
        """
        # Load events
        events = await self.config.event_store.get_events(
            session_id=session_id,
            run_id=run_id,
            from_seq_id=from_seq_id,
        )

        if mode == "dry_run":
            # Just return events, don't execute
            return events

        # Execute mode: would need to reconstruct agent and re-run
        # For now, just return events
        logger.info(f"Replay {len(events)} events from {session_id}/{run_id}")
        return events

    async def get_task(self, task_id: str) -> Optional[TaskHandle]:
        """Get a task by ID."""
        async with self._task_lock:
            return self._tasks.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.cancel()
                return True
        return False

    async def shutdown(self) -> None:
        """Shutdown runtime and clean up resources."""
        # Cancel all tasks
        async with self._task_lock:
            for task in list(self._tasks.values()):
                task.cancel()
            self._tasks.clear()

        logger.info("Runtime shutdown complete")


@dataclass
class RuntimeSession:
    """
    A session in runtime.

    Represents a single user session with potentially
    multiple runs.
    """

    session_id: str
    runtime: Runtime

    async def run_agent(self, agent: Agent, input_event: Event, run_id: Optional[str] = None):
        """Run an agent in this session."""
        return await self.runtime.run(
            agent=agent,
            session_id=self.session_id,
            input_event=input_event,
            run_id=run_id,
        )

    async def get_events(self, run_id: Optional[str] = None) -> List[Event]:
        """Get events for this session."""
        return await self.runtime.config.event_store.get_events(
            session_id=self.session_id,
            run_id=run_id,
        )


def create_runtime(
    agent: Agent,
    config: Optional[Dict[str, Any]] = None,
) -> Runtime:
    """
    Factory function to create a configured Runtime.

    Args:
        agent: Agent to use
        config: Configuration dictionary

    Returns:
        Configured Runtime instance
    """
    config = config or {}

    # Create storage
    from jarvis_core.store.event_store import MemoryEventStore
    from jarvis_core.store.state_store import MemoryStateStore

    event_store = config.get("event_store") or MemoryEventStore()
    state_store = config.get("state_store") or MemoryStateStore()

    # Create executor
    executor = config.get("executor") or RealExecutor()

    # Configure LLM executor if provided
    if "llm" in config and isinstance(executor, RealExecutor):
        llm_config = config["llm"]
        llm_type = llm_config.get("type", "mock")

        from jarvis_core.executor.llm_executor import create_llm_executor
        executor.llm_executor = create_llm_executor(
            executor_type=llm_type,
            **llm_config.get("config", {}),
        )
        executor.set_mock_response(
            "tool_call",
            {"result": "Tool executed successfully"}
        )

    # Create snapshot manager
    snapshot_manager = None
    if config.get("enable_snapshots", True):
        from jarvis_core.store.snapshot import SnapshotManager

        snapshot_manager = SnapshotManager(state_store=state_store)

    # Create runtime
    runtime_config = RuntimeConfig(
        event_store=event_store,
        state_store=state_store,
        executor=executor,
        snapshot_manager=snapshot_manager,
    )

    runtime = Runtime(runtime_config)

    return runtime
