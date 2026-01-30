"""Tests for Agent reducers."""

import pytest
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from jarvis_core import (
    Agent, SimpleChatAgent, AgentState,
    Event, EventType,
    Effect, EffectType,
)


class TestSimpleChatAgent:
    """Test simple chat agent."""

    def test_reduce_user_input(self):
        """Test handling user input event."""
        agent = SimpleChatAgent(
            system_prompt="You are a test assistant.",
        )

        state = AgentState(session_id="test")

        event = Event.new(
            session_id="test",
            agent_id=agent.id,
            run_id="test",
            type="user_input",
            payload={"message": "Hello!"},
        )

        new_state, effects = agent.reduce(state, event)

        # Check state was updated
        assert new_state.status == "running"
        assert len(new_state.history) == 1
        assert new_state.history[0]["role"] == "user"
        assert new_state.history[0]["content"] == "Hello!"

        # Check effects were created
        assert len(effects) > 0
        assert any(e.type == EffectType.LLM_STREAM for e in effects)

    def test_reduce_llm_response(self):
        """Test handling LLM response event."""
        agent = SimpleChatAgent()

        # Create state with user message
        state = AgentState(
            session_id="test",
            history=[
                {"role": "user", "content": "Hello!", "timestamp": 100.0}
            ],
        )

        event = Event.new(
            session_id="test",
            agent_id=agent.id,
            run_id="test",
            type="llm_response",
            payload={"response": "Hi there!"},
        )

        new_state, effects = agent.reduce(state, event)

        # Check state is idle
        assert new_state.status == "idle"
        assert len(new_state.history) == 2
        assert new_state.history[1]["role"] == "assistant"
        assert new_state.history[1]["content"] == "Hi there!"

        # Check save state effect
        assert any(e.type == EffectType.SAVE_STATE for e in effects)

    def test_state_serialization(self):
        """Test state to_dict and from_dict."""
        state = AgentState(
            session_id="test",
            user_id="user123",
        )

        # Convert to dict
        state_dict = state.to_dict()
        assert state_dict["session_id"] == "test"
        assert state_dict["user_id"] == "user123"
        assert "status" in state_dict

        # Convert back
        restored = AgentState.from_dict(state_dict)
        assert restored.session_id == "test"
        assert restored.user_id == "user123"
