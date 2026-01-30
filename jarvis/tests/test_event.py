"""Tests for Event system."""

import pytest
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from jarvis_core import Event, EventType, SystemEvents


class TestEvent:
    """Test Event creation and manipulation."""

    def test_event_creation(self):
        """Test creating events with Event.new factory."""
        event = Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="test_run",
            type=EventType.TOKEN,
            payload={"token": "hello"},
        )

        assert event.session_id == "test_session"
        assert event.agent_id == "test_agent"
        assert event.run_id == "test_run"
        assert event.type == EventType.TOKEN
        assert event.payload == {"token": "hello"}
        assert event.event_id is not None
        assert event.correlation_id is not None

    def test_event_immutability(self):
        """Test that events are immutable (frozen dataclass)."""
        event = Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="test_run",
            type=EventType.TOKEN,
            payload={"token": "hello"},
        )

        with pytest.raises(Exception):  # dataclass frozen=True
            event.payload = {"changed": True}

    def test_event_with_seq_id(self):
        """Test creating event with sequence ID."""
        event = Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="test_run",
            type=EventType.TOKEN,
        )

        event_with_seq = event.with_seq(5)

        assert event_with_seq.seq_id == 5
        assert event_with_seq.session_id == event.session_id
        assert event_with_seq.type == event.type

    def test_event_type_enums(self):
        """Test event type enums."""
        assert EventType.TOKEN == "token"
        assert EventType.TOOL_START == "tool_start"
        assert EventType.ERROR == "error"

        assert SystemEvents.WORKFLOW_STARTED == "workflow_started"
        assert SystemEvents.STREAM_TOKEN == "stream_token"
