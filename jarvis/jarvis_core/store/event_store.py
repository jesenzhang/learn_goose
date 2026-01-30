"""
Event Store - Persistent storage for events.

Events are append-only and never modified.
This is the single source of truth for the system.
"""

import abc
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import json

from jarvis_core.core.event import Event


class EventStore(abc.ABC):
    """
    Abstract base for event storage.

    EventStore provides:
    - Append events
    - Query events
    - Stream events
    - Replay events
    """

    @abc.abstractmethod
    async def append(self, event: Event) -> None:
        """Append an event to the store."""
        pass

    @abc.abstractmethod
    async def get_events(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_seq_id: int = 0,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Get events from the store."""
        pass

    @abc.abstractmethod
    async def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """Get a specific event by ID."""
        pass

    @abc.abstractmethod
    async def stream_events(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        from_seq_id: int = 0,
    ) -> Any:
        """Stream events as they are appended."""
        pass

    @abc.abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """Clear all events for a session."""
        pass


@dataclass
class MemoryEventStore(EventStore):
    """
    In-memory event store.

    Useful for testing and development.
    """

    _events: Dict[str, List[Event]] = None
    _by_id: Dict[str, Event] = None

    def __post_init__(self):
        self._events = {}
        self._by_id = {}

    async def append(self, event: Event) -> None:
        """Append an event to the store."""
        key = f"{event.session_id}:{event.run_id}"
        if key not in self._events:
            self._events[key] = []

        # Set seq_id
        seq_id = len(self._events[key])
        event_with_seq = Event(
            session_id=event.session_id,
            agent_id=event.agent_id,
            run_id=event.run_id,
            type=event.type,
            seq_id=seq_id,
            event_id=event.event_id,
            payload=event.payload,
            causation_id=event.causation_id,
            correlation_id=event.correlation_id,
            timestamp=event.timestamp,
            metadata=event.metadata,
        )

        self._events[key].append(event_with_seq)
        self._by_id[event.event_id] = event_with_seq

    async def get_events(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_seq_id: int = 0,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Get events from the store."""
        if run_id:
            key = f"{session_id}:{run_id}"
            events = self._events.get(key, [])
        else:
            # Get all events for session (across all runs)
            events = []
            for k, evts in self._events.items():
                if k.startswith(f"{session_id}:"):
                    events.extend(evts)

        # Filter by seq_id
        events = [e for e in events if e.seq_id >= from_seq_id]

        # Filter by type
        if event_type:
            events = [e for e in events if e.type == event_type]

        # Sort by seq_id
        events = sorted(events, key=lambda e: e.seq_id)

        # Limit
        if limit:
            events = events[:limit]

        return events

    async def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """Get a specific event by ID."""
        return self._by_id.get(event_id)

    async def stream_events(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        from_seq_id: int = 0,
    ) -> Any:
        """Stream events as they are appended."""
        # For memory store, just return the events
        return await self.get_events(
            session_id=session_id,
            run_id=run_id,
            from_seq_id=from_seq_id,
        )

    async def clear_session(self, session_id: str) -> None:
        """Clear all events for a session."""
        keys_to_remove = [k for k in self._events.keys() if k.startswith(f"{session_id}:")]
        for key in keys_to_remove:
            for event in self._events[key]:
                del self._by_id[event.event_id]
            del self._events[key]


@dataclass
class SQLiteEventStore(EventStore):
    """
    SQLite-based persistent event store.

    Provides durable storage for events.
    """

    db_path: str = ":memory:"
    _conn: Any = None

    def __post_init__(self):
        self._initialized = False

    async def _initialize(self):
        """Initialize the database."""
        if self._initialized:
            return

        import aiosqlite

        self._conn = await aiosqlite.connect(self.db_path)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                type TEXT NOT NULL,
                seq_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                causation_id TEXT,
                correlation_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                metadata TEXT NOT NULL,
                UNIQUE(session_id, run_id, seq_id)
            )
        """)

        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS EXISTS_idx_session_run
            ON events(session_id, run_id)
        """)

        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session
            ON events(session_id)
        """)

        await self._conn.commit()
        self._initialized = True

    async def append(self, event: Event) -> None:
        """Append an event to the store."""
        await self._initialize()

        # Get next seq_id
        async with self._conn.execute(
            "SELECT COALESCE(MAX(seq_id), -1) + 1 FROM events WHERE session_id = ? AND run_id = ?",
            (event.session_id, event.run_id),
        ) as cursor:
            row = await cursor.fetchone()
            seq_id = row[0] if row else 0

        await self._conn.execute(
            """
            INSERT INTO events (
                event_id, session_id, run_id, agent_id, type, seq_id,
                payload, causation_id, correlation_id, timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.session_id,
                event.run_id,
                event.agent_id,
                event.type,
                seq_id,
                json.dumps(event.payload),
                event.causation_id,
                event.correlation_id,
                event.timestamp,
                json.dumps(event.metadata),
            ),
        )
        await self._conn.commit()

    async def get_events(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_seq_id: int = 0,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Get events from the store."""
        await self._initialize()

        query = """
            SELECT event_id, session_id, run_id, agent_id, type, seq_id,
                   payload, causation_id, correlation_id, timestamp, metadata
            FROM events
            WHERE session_id = ? AND seq_id >= ?
        """
        params = [session_id, from_seq_id]

        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)

        if event_type:
            query += " AND type = ?"
            params.append(event_type)

        query += " ORDER BY seq_id ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        events = []
        async with self._conn.execute(query, params) as cursor:
            async for row in cursor:
                events.append(Event(
                    event_id=row[0],
                    session_id=row[1],
                    run_id=row[2],
                    agent_id=row[3],
                    type=row[4],
                    seq_id=row[5],
                    payload=json.loads(row[6]),
                    causation_id=row[7],
                    correlation_id=row[8],
                    timestamp=row[9],
                    metadata=json.loads(row[10]),
                ))

        return events

    async def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """Get a specific event by ID."""
        await self._initialize()

        async with self._conn.execute(
            "SELECT event_id, session_id, run_id, agent_id, type, seq_id, payload, causation_id, correlation_id, timestamp, metadata FROM events WHERE event_id = ?",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Event(
                    event_id=row[0],
                    session_id=row[1],
                    run_id=row[2],
                    agent_id=row[3],
                    type=row[4],
                    seq_id=row[5],
                    payload=json.loads(row[6]),
                    causation_id=row[7],
                    correlation_id=row[8],
                    timestamp=row[9],
                    metadata=json.loads(row[10]),
                )
        return None

    async def stream_events(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        from_seq_id: int = 0,
    ) -> Any:
        """Stream events as they are appended."""
        return await self.get_events(
            session_id=session_id,
            run_id=run_id,
            from_seq_id=from_seq_id,
        )

    async def clear_session(self, session_id: str) -> None:
        """Clear all events for a session."""
        await self._initialize()
        await self._conn.execute(
            "DELETE FROM events WHERE session_id = ?",
            (session_id,),
        )
        await self._conn.commit()

    async def close(self):
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
