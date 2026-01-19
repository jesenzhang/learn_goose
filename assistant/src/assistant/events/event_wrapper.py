"""Event wrapper for backward compatibility."""
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import time

from .types import Event as StreamerEvent


class Event(BaseModel):
    """
    Event model compatible with original assistant API.

    This is a wrapper around StreamerEvent that maintains the original
    Event interface while using BaseStreamer internally.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: str = None  # Changed from Enum to str for flexibility
    data: Any = None
    timestamp: float = Field(default_factory=time.time)
    meta: Optional[Dict[str, Any]] = None

    @classmethod
    def from_streamer_event(cls, streamer_event: StreamerEvent) -> "Event":
        """Convert StreamerEvent to Event."""
        return cls(
            id=streamer_event.id,
            type=streamer_event.type,
            data=streamer_event.data,
            timestamp=streamer_event.timestamp,
            meta={
                "run_id": streamer_event.run_id,
                "seq_id": streamer_event.seq_id,
                "producer_id": streamer_event.producer_id,
                "parent_run_id": streamer_event.parent_run_id,
                **streamer_event.metadata
            }
        )

    def to_streamer_event(self, run_id: str, seq_id: int) -> StreamerEvent:
        """Convert Event to StreamerEvent."""
        meta = self.meta or {}
        return StreamerEvent(
            id=self.id,
            run_id=run_id,
            seq_id=seq_id,
            type=self.type,
            data=self.data,
            timestamp=self.timestamp,
            producer_id=meta.get("producer_id"),
            parent_run_id=meta.get("parent_run_id"),
            metadata={k: v for k, v in meta.items()
                     if k not in ["run_id", "seq_id", "producer_id", "parent_run_id"]}
        )
