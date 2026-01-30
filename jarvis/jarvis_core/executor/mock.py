"""
Mock Executor - For testing purposes.

MockExecutor returns predefined responses without
actually executing effects.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from jarvis_core.core.effect import Effect, EffectType
from jarvis_core.core.event import Event


@dataclass
class MockExecutor:
    """
    Mock executor for testing.

    Returns predefined responses for all effects.
    """

    # Mock responses
    mock_responses: Dict[str, Any] = None
    default_response: Any = "mock_result"

    def __post_init__(self):
        if self.mock_responses is None:
            self.mock_responses = {}

    async def execute(
        self,
        effect: Effect,
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> Event:
        """Execute effect and return mock event."""
        # Get mock response
        response = self.mock_responses.get(effect.effect_type.value, self.default_response)

        # Create appropriate event
        if effect.effect_type == EffectType.TOOL_CALL:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="tool_end",
                payload={
                    "tool_name": effect.payload.get("tool_name"),
                    "result": response,
                    "is_error": False,
                    "mock": True,
                },
            )

        elif effect.effect_type == EffectType.LLM_GENERATE:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="assistant_response",
                payload={
                    "message": response,
                    "mock": True,
                },
            )

        elif effect.effect_type == EffectType.LLM_STREAM:
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                type="assistant_response",
                payload={
                    "message": response,
                    "mock": True,
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
                    "result": response,
                    "mock": True,
                },
            )

    async def execute_batch(
        self,
        effects: List[Effect],
        session_id: str,
        agent_id: str,
        run_id: str,
    ) -> List[Event]:
        """Execute multiple effects (returns mock events)."""
        return [
            await self.execute(effect, session_id, agent_id, run_id)
            for effect in effects
        ]

    def set_mock_response(self, effect_type: str, response: Any) -> None:
        """Set a mock response for a specific effect type."""
        self.mock_responses[effect_type] = response
