"""
Events Package - Unified event system.

Provides:
1. BaseStreamer - Advanced streaming with backfill and seq_id support
2. Event adapters - Convert between event models
3. Legacy Event types for backward compatibility
"""

# Legacy exports (event types for backward compatibility)
from .legacy import EventType
from .event_wrapper import Event

# New exports (BaseStreamer functionality)
from .types import Event as StreamerEvent
from .streamer import BaseStreamer, IStreamer
from .bus import MemoryEventBus, IEventBus
from .store import AsyncEventStore, IEventStore
from .factory import StreamerFactory
from .replay import EventReplayManager, ReplayMode

# Unified exports for convenience
# Event defaults to the wrapped Event for backward compatibility
__all__ = [
    # Legacy (event types)
    "EventType",
    "Event",

    # New (BaseStreamer)
    "StreamerEvent",
    "BaseStreamer",
    "IStreamer",
    "MemoryEventBus",
    "IEventBus",
    "AsyncEventStore",
    "IEventStore",
    "StreamerFactory",
    "EventReplayManager",
    "ReplayMode",
]
