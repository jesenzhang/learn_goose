"""
Events Package - Unified event system.

Provides:
1. Legacy EventManager - Original implementation (fully backward compatible)
2. BaseStreamer - Advanced streaming with backfill and seq_id support
3. Event adapters - Convert between event models
"""

# Legacy exports (original API - no changes required)
from .legacy import EventType
from .event_manager import EventManager
from .event_wrapper import Event

# New exports (BaseStreamer functionality)
from .types import Event as StreamerEvent
from .streamer import BaseStreamer, IStreamer
from .bus import MemoryEventBus, IEventBus
from .store import AsyncEventStore, IEventStore
from .factory import StreamerFactory

# Unified exports for convenience
# Event defaults to the wrapped Event for backward compatibility
__all__ = [
    # Legacy (original API)
    "EventManager",
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
]
