"""
Effect Executor - Executes effects and produces events.

The executor is responsible for:
1. Taking effects from agent
2. Executing the side effects
3. Producing events
4. Handling errors, retries, timeouts
"""

import abc
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from jarvis_core.core.effect import Effect, EffectType
from jarvis_core.core.event import Event


class ExecutionStatus(str, Enum):
    """Status of effect execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    """
    Result of executing an effect.

    Contains:
    - Status
    - Output data
    - Error information
    - Metadata
    """

    effect_id: str
    status: ExecutionStatus

    # Output
    output: Optional[Any] = None

    # Error handling
    error: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0

    # Timing
    duration_seconds: float = 0.0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "effect_id": self.effect_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "retry_count": self.retry_count,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


class EffectExecutor(abc.ABC):
    """
    Abstract base for effect executors.

    An EffectExecutor:
    1. Receives effects from agents
    2. Executes them (with retry/timeout)
    3. Produces events
    4. Handles errors gracefully
    """

    @abc.abstractmethod
    async def execute(
        self,
        effect: Effect,
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> Event:
        """
        Execute an effect and produce an event.

        This method must:
        1. Execute the effect with retry/timeout
        2. Return an Event describing the result

        The event should follow these patterns:
        - LLM effects → token events
        - Tool effects → tool_end events
        - State effects → state_change events
        - Error → error events
        """
        pass

    @abc.abstractmethod
    async def execute_batch(
        self,
        effects: List[Effect],
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> List[Event]:
        """
        Execute multiple effects in parallel.

        Returns events for all effects.
        """
        pass


@dataclass
class RealExecutor(EffectExecutor):
    """
    Real executor that actually executes effects.

    Handles:
    - Retry logic
    - Timeout handling
    - Error recovery
    """

    # Tool registry
    tools: Dict[str, Callable] = field(default_factory=dict)

    # LLM executor (optional, for LLM effects)
    llm_executor: Optional[Any] = None

    # Custom handlers
    custom_handlers: Dict[EffectType, Callable] = field(default_factory=dict)

    def register_tool(self, name: str, handler: Callable) -> None:
        """Register a tool handler."""
        self.tools[name] = handler

    def register_custom_handler(self, effect_type: EffectType, handler: Callable) -> None:
        """Register a custom effect handler."""
        self.custom_handlers[effect_type] = handler

    async def execute(
        self,
        effect: Effect,
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> Event:
        """
        Execute an effect with retry/timeout.
        """
        import time
        start_time = time.time()

        for attempt in range(effect.retry + 1):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self._execute_once(effect, session_id, agent_id, run_id),
                    timeout=effect.timeout,
                )

                duration = time.time() - start_time

                # Create success event
                return self._create_success_event(
                    effect=effect,
                    result=result,
                    session_id=session_id,
                    agent_id=agent_id,
                    run_id=run_id,
                    duration=duration,
                )

            except asyncio.TimeoutError:
                if attempt < effect.retry:
                    # Retry
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    # Timeout failed
                    duration = time.time() - start_time
                    return self._create_error_event(
                        effect=effect,
                        error="Execution timeout",
                        error_type="TimeoutError",
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        duration=duration,
                    )

            except Exception as e:
                if attempt < effect.retry:
                    # Retry
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    # Failed
                    duration = time.time() - start_time
                    return self._create_error_event(
                        effect=effect,
                        error=str(e),
                        error_type=type(e).__name__,
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        duration=duration,
                    )

        # Should not reach here
        duration = time.time() - start_time
        return self._create_error_event(
            effect=effect,
            error="Max retries exceeded",
            error_type="RetryExceededError",
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            duration=duration,
        )

    async def _execute_once(
        self,
        effect: Effect,
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> Any:
        """Execute effect once (no retry logic)."""
        # Check custom handler
        if effect.effect_type in self.custom_handlers:
            handler = self.custom_handlers[effect.effect_type]
            return await handler(effect, session_id, agent_id, run_id)

        # Handle built-in effect types
        if effect.effect_type == EffectType.TOOL_CALL:
            return await self._execute_tool(effect)

        elif effect.effect_type == EffectType.LLM_GENERATE:
            if self.llm_executor:
                return await self.llm_executor.execute(effect)
            else:
                raise NotImplementedError("LLM executor not configured")

        elif effect.effect_type == EffectType.LLM_STREAM:
            if self.llm_executor:
                return await self.llm_executor.execute_stream(effect)
            else:
                raise NotImplementedError("LLM executor not configured")

        elif effect.effect_type == EffectType.SAVE_STATE:
            # State effects are handled by runtime, not executor
            return {"status": "deferred"}

        else:
            raise NotImplementedError(f"Unknown effect type: {effect.effect_type}")

    async def _execute_tool(self, effect: Effect) -> Any:
        """Execute a tool effect."""
        tool_name = effect.payload.get("tool_name")
        tool_args = effect.payload.get("tool_args", {})

        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        handler = self.tools[tool_name]
        result = handler(**tool_args)

        # If handler is async, await it
        if asyncio.iscoroutine(result):
            result = await result

        return result

    def _create_success_event(
        self,
        effect: Effect,
        result: Any,
        session_id: str,
        agent_id: str,
        run_id: str,
        duration: float,
    ) -> Event:
        """Create an event for successful execution."""
        from jarvis_core.core.event import EventType

        if effect.effect_type == EffectType.TOOL_CALL:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="tool_end",
                payload={
                    "tool_name": effect.payload.get("tool_name"),
                    "result": result,
                    "is_error": False,
                    "duration": duration,
                },
            )

        elif effect.effect_type == EffectType.LLM_GENERATE:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="assistant_response",
                payload={
                    "message": result,
                    "duration": duration,
                },
            )

        elif effect.effect_type == EffectType.LLM_STREAM:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="assistant_response",
                payload={
                    "message": result,
                    "duration": duration,
                },
            )

        else:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="effect_completed",
                payload={
                    "effect_type": effect.effect_type.value,
                    "result": result,
                    "duration": duration,
                },
            )

    def _create_error_event(
        self,
        effect: Effect,
        error: str,
        error_type: str,
        session_id: str,
        agent_id: str,
        run_id: str,
        duration: float,
    ) -> Event:
        """Create an event for failed execution."""
        from jarvis_core.core.event import EventType

        if effect.effect_type == EffectType.TOOL_CALL:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="tool_end",
                payload={
                    "tool_name": effect.payload.get("tool_name"),
                    "result": None,
                    "is_error": True,
                    "error": error,
                    "error_type": error_type,
                    "duration": duration,
                },
            )

        else:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="error",
                payload={
                    "error": error,
                    "error_type": error_type,
                    "effect_type": effect.effect_type.value,
                    "duration": duration,
                },
            )

    async def execute_batch(
        self,
        effects: List[Effect],
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> List[Event]:
        """Execute multiple effects in parallel."""
        tasks = [
            self.execute(effect, session_id, agent_id, run_id)
            for effect in effects
        ]
        return await asyncio.gather(*tasks)
