"""
Snapshot Manager - Automatic snapshot management.

SnapshotManager periodically saves snapshots to:
- Enable fast recovery
- Support time travel
- Reduce replay time for long runs
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable
import uuid

from jarvis_core.core.state import AgentState, Snapshot
from jarvis_core.store.state_store import StateStore


@dataclass
class SnapshotConfig:
    """Configuration for snapshot manager."""

    # Trigger conditions
    min_events: int = 10  # Minimum events between snapshots
    min_time_seconds: float = 30.0  # Minimum time between snapshots

    # Size limits
    max_snapshots_per_run: int = 10  # Maximum snapshots to keep per run

    # Auto-snapshot
    auto_snapshot: bool = True  # Enable automatic snapshoting


@dataclass
class SnapshotManager:
    """
    Manages automatic snapshot creation and cleanup.

    The SnapshotManager:
    1. Monitors event count and time
    2. Creates snapshots when thresholds are reached
    3. Cleans up old snapshots
    """

    state_store: StateStore
    config: SnapshotConfig = field(default_factory=SnapshotConfig)

    # State tracking
    _event_count: int = field(init=False, default=0)
    _last_snapshot_time: float = field(init=False, default=0)
    _run_snapshots: dict[str, list[str]] = field(init=False, default_factory=dict)

    def __post_init__(self):
        import time
        self._last_snapshot_time = time.time()

    async def should_snapshot(
        self,
        session_id: str,
        run_id: str,
    ) -> bool:
        """
        Check if a snapshot should be created.

        Returns True if any trigger condition is met.
        """
        if not self.config.auto_snapshot:
            return False

        import time

        # Check event count
        if self._event_count >= self.config.min_events:
            return True

        # Check time
        time_since_snapshot = time.time() - self._last_snapshot_time
        if time_since_snapshot >= self.config.min_time_seconds:
            return True

        return False

    async def create_snapshot(
        self,
        state: AgentState,
        seq_id: int,
        metadata: Optional[dict] = None,
    ) -> Snapshot:
        """
        Create a new snapshot.

        Updates tracking state and cleans up old snapshots.
        """
        import time

        # Create snapshot
        snapshot = Snapshot(
            snapshot_id=uuid.uuid4().hex,
            state=state,
            seq_id=seq_id,
            created_at=time.time(),
            metadata=metadata or {},
        )

        # Save to store
        await self.state_store.save_snapshot(snapshot)

        # Update tracking
        self._event_count = 0
        self._last_snapshot_time = time.time()

        run_key = f"{state.session_id}:{state.run_id}"
        if run_key not in self._run_snapshots:
            self._run_snapshots[run_key] = []
        self._run_snapshots[run_key].append(snapshot.snapshot_id)

        # Cleanup old snapshots
        await self._cleanup_old_snapshots(run_key)

        return snapshot

    def record_event(self) -> None:
        """Record that an event was processed."""
        self._event_count += 1

    async def load_snapshot_for_time_travel(
        self,
        session_id: str,
        run_id: str,
        target_seq_id: int,
    ) -> Optional[Snapshot]:
        """
        Load the best snapshot for time travel.

        Returns the snapshot with highest seq_id <= target_seq_id.
        """
        run_key = f"{session_id}:{run_id}"
        snapshot_ids = self._run_snapshots.get(run_key, [])

        best_snapshot = None
        best_seq_id = -1

        for snapshot_id in snapshot_ids:
            snapshot = await self.state_store.load_snapshot(snapshot_id)
            if snapshot and snapshot.seq_id <= target_seq_id:
                if snapshot.seq_id > best_seq_id:
                    best_snapshot = snapshot
                    best_seq_id = snapshot.seq_id

        return best_snapshot

    async def _cleanup_old_snapshots(self, run_key: str) -> None:
        """Remove old snapshots if we exceed the limit."""
        snapshot_ids = self._run_snapshots.get(run_key, [])

        if len(snapshot_ids) > self.config.max_snapshots_per_run:
            # Remove oldest snapshots
            to_remove = len(snapshot_ids) - self.config.max_snapshots_per_run
            for i in range(to_remove):
                old_snapshot_id = snapshot_ids.pop(0)
                # Note: We don't delete from store to keep history
                # Just remove from tracking

    async def get_snapshot_count(
        self,
        session_id: str,
        run_id: str,
    ) -> int:
        """Get the number of snapshots for a run."""
        run_key = f"{session_id}:{run_id}"
        return len(self._run_snapshots.get(run_key, []))

    async def clear_run(
        self,
        session_id: str,
        run_id: str,
    ) -> None:
        """Clear snapshot tracking for a run."""
        run_key = f"{session_id}:{run_id}"
        if run_key in self._run_snapshots:
            del self._run_snapshots[run_key]
