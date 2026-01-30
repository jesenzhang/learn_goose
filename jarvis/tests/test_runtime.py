"""Tests for Runtime engine."""

import pytest
import asyncio
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from jarvis_core import (
    Runtime, create_runtime,
    Agent, SimpleChatAgent,
    Event, EventType,
    AgentStatus,
)


class TestRuntime:
    """Test Runtime execution."""

    @pytest.mark.asyncio
    async def test_run_simple_agent(self):
        """Test running a simple agent."""
        agent = SimpleChatAgent()

        runtime = create_runtime(
            agent=agent,
            config={
                "executor": "mock",
                "event_store": "memory",
            },
        )

        session_id = "test_session"

        # Create input event
        input_event = Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id="test_run",
            type="user_input",
            payload={"message": "Test message"},
        )

        # Run task
        handle = await runtime.run(
            session_id=session_id,
            input_event=input_event,
        )

        # Wait for completion
        while handle.is_running:
            await asyncio.sleep(0.01)

        # Verify completed successfully
        assert handle.is_done
        assert not handle.is_failed

        # Verify events were stored
        events = []
        async for event in runtime._event_store.load(session_id, "test_run"):
            events.append(event)

        assert len(events) >= 2  # At least input + response
        assert events[0].type == "user_input"

        # Cleanup
        await runtime.close()

    @pytest.mark.asyncio
    async def test_event_callbacks(self):
        """Test event callback registration."""
        agent = SimpleChatAgent()
        runtime = create_runtime(agent=agent, config={"executor": "mock"})

        # Track received events
        received_events = []

        def callback(event):
            received_events.append(event)

        runtime.on_event(callback)

        session_id = "callback_test"
        input_event = Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id="test_run",
            type="user_input",
            payload={"message": "Test"},
        )

        handle = await runtime.run(
            session_id=session_id,
            input_event=input_event,
        )

        while handle.is_running:
            await asyncio.sleep(0.01)

        # Verify callback received events
        assert len(received_events) > 0

        await runtime.close()

    @pytest.mark.asyncio
    async def test_multiple_sessions(self):
        """Test running multiple concurrent sessions."""
        agent = SimpleChatAgent()
        runtime = create_runtime(agent=agent, config={"executor": "mock"})

        handles = []

        # Create 3 concurrent sessions
        for i in range(3):
            session_id = f"session_{i}"
            input_event = Event.new(
                session_id=session_id,
                agent_id=agent.id,
                run_id=f"run_{i}",
                type="user_input",
                payload={"message": f"Message {i}"},
            )

            handle = await runtime.run(
                session_id=session_id,
                input_event=input_event,
            )
            handles.append(handle)

        # Wait for all to complete
        for handle in handles:
            while handle.is_running:
                await asyncio.sleep(0.01)

        # Verify all completed
        assert all(h.is_done for h in handles)

        # Verify sessions
        sessions = await runtime.list_sessions()
        assert len(sessions) == 3

        await runtime.close()
