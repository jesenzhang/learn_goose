"""Tests for Event and State storage."""

import pytest
import asyncio
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from jarvis_core import (
    Event, EventStore, StateStore,
    MemoryEventStore, MemoryStateStore,
    AgentState, Snapshot,
)


class TestMemoryEventStore:
    """Test in-memory event store."""

    @pytest.mark.asyncio
    async def test_append_and_load(self):
        """Test appending and loading events."""
        store = MemoryEventStore()

        event1 = Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="test_run",
            type="test_event",
            payload={"seq": 1},
        )

        event2 = Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="test_run",
            type="test_event",
            payload={"seq": 2},
        )

        await store.append(event1)
        await store.append(event2)

        # Load all events
        events = []
        async for event in store.load("test_session", "test_run"):
            events.append(event)

        assert len(events) == 2
        assert events[0].seq_id == 1
        assert events[1].seq_id == 2

    @pytest.mark.asyncio
    async def test_load_after_seq_id(self):
        """Test loading events after a specific sequence."""
        store = MemoryEventStore()

        for i in range(5):
            event = Event.new(
                session_id="test_session",
                agent_id="test_agent",
                run_id="test_run",
                type="test_event",
                payload={"seq": i},
            )
            await store.append(event)

        # Load after seq 3
        events = []
        async for event in store.load("test_session", "test_run", after_seq_id=3):
            events.append(event)

        assert len(events) == 2  # seq 4 and 5
        assert events[0].seq_id == 4
        assert events[1].seq_id == 5

    @pytest.mark.asyncio
    async def test_multiple_runs(self):
        """Test events from multiple runs."""
        store = MemoryEventStore()

        # Run 1
        await store.append(Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="run_1",
            type="test_event",
            payload={"run": 1},
        ))

        # Run 2
        await store.append(Event.new(
            session_id="test_session",
            agent_id="test_agent",
            run_id="run_2",
            type="test_event",
            payload={"run": 2},
        ))

        # Load specific run
        events = []
        async for event in store.load("test_session", "run_1"):
            events.append(event)

        assert len(events) == 1
        assert events[0].payload == {"run": 1}


class TestMemoryStateStore:
    """Test in-memory state store."""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test saving and loading state."""
        store = MemoryStateStore()

        state = AgentState(
            session_id="test_session",
            user_id="test_user",
        )

        await store.save_state("test_session", state)

        loaded = await store.load_state("test_session")

        assert loaded is not None
        assert loaded.session_id == "test_session"
        assert loaded.user_id == "test_user"

    @pytest.mark.asyncio
    async def test_snapshots(self):
        """Test saving and loading snapshots."""
        store = MemoryStateStore()

        snapshot1 = Snapshot(
            session_id="test_session",
            run_id="test_run",
            seq_id=1,
            timestamp=100.0,
            state={"key": "value1"},
        )

        snapshot2 = Snapshot(
            session_id="test_session",
            run_id="test_run",
            seq_id=2,
            timestamp=200.0,
            state={"key": "value2"},
        )

        await store.save_snapshot(snapshot1)
        await store.save_snapshot(snapshot2)

        # Load latest
        latest = await store.load_latest_snapshot("test_session", "test_run")

        assert latest is not None
        assert latest.seq_id == 2
        assert latest.state == {"key": "value2"}

        # List all
        snapshots = await store.list_snapshots("test_session", "test_run")

        assert len(snapshots) == 2
        assert snapshots[0].seq_id == 1
        assert snapshots[1].seq_id == 2
