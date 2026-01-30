"""
State Store - Storage for agent states and snapshots.

StateStore provides:
- Save state
- Load state
- Manage snapshots
"""

import abc
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json

from jarvis_core.core.state import AgentState, Snapshot


class StateStore(abc.ABC):
    """
    Abstract base for state storage.
    """

    @abc.abstractmethod
    async def save_state(
        self,
        session_id: str,
        run_id: str,
        state: AgentState,
    ) -> None:
        """Save a state."""
        pass

    @abc.abstractmethod
    async def load_state(
        self,
        session_id: str,
        run_id: str,
    ) -> Optional[AgentState]:
        """Load a state."""
        pass

    @abc.abstractmethod
    async def save_snapshot(
        self,
        snapshot: Snapshot,
    ) -> None:
        """Save a snapshot."""
        pass

    @abc.abstractmethod
    async def load_snapshot(
        self,
        snapshot_id: str,
    ) -> Optional[Snapshot]:
        """Load a snapshot."""
        pass

    @abc.abstractmethod
    async def get_latest_snapshot(
        self,
        session_id: str,
        run_id: str,
    ) -> Optional[Snapshot]:
        """Get the latest snapshot for a run."""
        pass

    @abc.abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """Clear all data for a session."""
        pass


@dataclass
class MemoryStateStore(StateStore):
    """
    In-memory state store.

    Useful for testing and development.
    """

    _states: Dict[str, AgentState] = None
    _snapshots: Dict[str, Snapshot] = None
    _run_snapshots: Dict[str, List[str]] = None

    def __post_init__(self):
        self._states = {}
        self._snapshots = {}
        self._run_snapshots = {}

    def _get_state_key(self, session_id: str, run_id: str) -> str:
        return f"{session_id}:{run_id}"

    async def save_state(
        self,
        session_id: str,
        run_id: str,
        state: AgentState,
    ) -> None:
        """Save a state."""
        key = self._get_state_key(session_id, run_id)
        self._states[key] = state

    async def load_state(
        self,
        session_id: str,
        run_id: str,
    ) -> Optional[AgentState]:
        """Load a state."""
        key = self._get_state_key(session_id, run_id)
        return self._states.get(key)

    async def save_snapshot(
        self,
        snapshot: Snapshot,
    ) -> None:
        """Save a snapshot."""
        self._snapshots[snapshot.snapshot_id] = snapshot

        # Track by run
        run_key = f"{snapshot.state.session_id}:{snapshot.state.run_id}"
        if run_key not in self._run_snapshots:
            self._run_snapshots[run_key] = []
        self._run_snapshots[run_key].append(snapshot.snapshot_id)

    async def load_snapshot(
        self,
        snapshot_id: str,
    ) -> Optional[Snapshot]:
        """Load a snapshot."""
        return self._snapshots.get(snapshot_id)

    async def get_latest_snapshot(
        self,
        session_id: str,
        run_id: str,
    ) -> Optional[Snapshot]:
        """Get the latest snapshot for a run."""
        run_key = f"{session_id}:{run_id}"
        snapshot_ids = self._run_snapshots.get(run_key, [])
        if snapshot_ids:
            return self._snapshots.get(snapshot_ids[-1])
        return None

    async def clear_session(self, session_id: str) -> None:
        """Clear all data for a session."""
        # Clear states
        keys_to_remove = [k for k in self._states.keys() if k.startswith(f"{session_id}:")]
        for key in keys_to_remove:
            del self._states[key]

        # Clear run snapshots
        run_keys_to_remove = [k for k in self._run_snapshots.keys() if k.startswith(f"{session_id}:")]
        for run_key in run_keys_to_remove:
            for snapshot_id in self._run_snapshots[run_key]:
                del self._snapshots[snapshot_id]
            del self._run_snapshots[run_key]


@dataclass
class SQLiteStateStore(StateStore):
    """
    SQLite-based persistent state store.

    Provides durable storage for states and snapshots.
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
            CREATE TABLE IF NOT EXISTS states (
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                state_data TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (session_id, run_id)
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                seq_id INTEGER NOT NULL,
                state_data TEXT NOT NULL,
                created_at REAL NOT NULL,
                metadata TEXT NOT NULL
            )
        """)

        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_run
            ON snapshots(session_id, run_id, seq_id)
        """)

        await self._conn.commit()
        self._initialized = True

    async def save_state(
        self,
        session_id: str,
        run_id: str,
        state: AgentState,
    ) -> None:
        """Save a state."""
        await self._initialize()

        import time
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO states (session_id, run_id, state_data, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                session_id,
                run_id,
                json.dumps(state.to_dict()),
                time.time(),
            ),
        )
        await self._conn.commit()

    async def load_state(
        self,
        session_id: str,
        run_id: str,
    ) -> Optional[AgentState]:
        """Load a state."""
        await self._initialize()

        async with self._conn.execute(
            "SELECT state_data FROM states WHERE session_id = ? AND run_id = ?",
            (session_id, run_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return AgentState.from_dict(json.loads(row[0]))
        return None

    async def save_snapshot(
        self,
        snapshot: Snapshot,
    ) -> None:
        """Save a snapshot."""
        await self._initialize()

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO snapshots (
                snapshot_id, session_id, run_id, seq_id,
                state_data, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.state.session_id,
                snapshot.state.run_id,
                snapshot.seq_id,
                json.dumps(snapshot.state.to_dict()),
                snapshot.created_at,
                json.dumps(snapshot.metadata),
            ),
        )
        await self._conn.commit()

    async def load_snapshot(
        self,
        snapshot_id: str,
    ) -> Optional[Snapshot]:
        """Load a snapshot."""
        await self._initialize()

        async with self._conn.execute(
            """
            SELECT snapshot_id, session_id, run_id, seq_id,
                   state_data, created_at, metadata
            FROM snapshots WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                state = AgentState.from_dict(json.loads(row[4]))
                return Snapshot(
                    snapshot_id=row[0],
                    state=state,
                    seq_id=row[3],
                    created_at=row[5],
                    metadata=json.loads(row[6]),
                )
        return None

    async def get_latest_snapshot(
        self,
        session_id: str,
        run_id: str,
    ) -> Optional[Snapshot]:
        """Get the latest snapshot for a run."""
        await self._initialize()

        async with self._conn.execute(
            """
            SELECT snapshot_id, session_id, run_id, seq_id,
                   state_data, created_at, metadata
            FROM snapshots
            WHERE session_id = ? AND run_id = ?
            ORDER BY seq_id DESC
            LIMIT 1
            """,
            (session_id, run_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                state = AgentState.from_dict(json.loads(row[4]))
                return Snapshot(
                    snapshot_id=row[0],
                    state=state,
                    seq_id=row[3],
                    created_at=row[5],
                    metadata=json.loads(row[6]),
                )
        return None

    async def clear_session(self, session_id: str) -> None:
        """Clear all data for a session."""
        await self._initialize()

        await self._conn.execute(
            "DELETE FROM states WHERE session_id = ?",
            (session_id,),
        )
        await self._conn.execute(
            "DELETE FROM snapshots WHERE session_id = ?",
            (session_id,),
        )
        await self._conn.commit()

    async def close(self):
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
