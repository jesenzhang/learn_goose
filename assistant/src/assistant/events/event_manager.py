"""
EventManager wrapper using BaseStreamer internally.

This implementation maintains backward compatibility by directly calling listeners
on each emit(), while also using BaseStreamer for DB persistence.
"""
import asyncio
import logging
import weakref
from typing import Callable, Awaitable, List, Any, Optional, Dict

from .streamer import BaseStreamer
from .bus import MemoryEventBus
from .store import AsyncEventStore
from .event_wrapper import Event
from .factory import StreamerFactory

logger = logging.getLogger(__name__)


class EventManager:
    """
    EventManager that uses BaseStreamer internally for persistence,
    but maintains original direct-delivery behavior for compatibility.
    """

    def __init__(self, db_manager=None, bus=None, store=None):
        # Internal BaseStreamer instance (created lazily when needed)
        self._streamer: Optional[BaseStreamer] = None
        self._bus = bus or MemoryEventBus()
        self._store = store

        # Listener management for original API
        self._listeners: List[Callable[[Event], Awaitable[None]]] = []
        self._weak_listeners: List[weakref.ref] = []
        self._current_session_id: Optional[int] = None

    def _ensure_streamer(self, session_id: int) -> BaseStreamer:
        """Ensure streamer exists for given session."""
        if self._streamer is None or self._current_session_id != session_id:
            self._current_session_id = session_id
            factory = StreamerFactory(bus=self._bus, store=self._store)
            self._streamer = factory.create(str(session_id))
        return self._streamer

    async def _deliver_to_listeners(self, event: Event):
        """Deliver event to all registered listeners."""
        active_listeners = list(self._listeners)
        for weak_ref in self._weak_listeners:
            listener = weak_ref()
            if listener is not None:
                active_listeners.append(listener)

        if active_listeners:
            tasks = [listener(event) for listener in active_listeners]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Event listener error: {result}", exc_info=result)

    def subscribe(
        self,
        listener: Callable[[Event], Awaitable[None]],
        weak: bool = False
    ) -> Callable[[], None]:
        """
        Subscribe to events.

        Args:
            listener: Async callback that receives Event objects
            weak: If True, use weak reference

        Returns:
            Unsubscribe callback
        """
        if weak:
            weak_ref = weakref.ref(listener, self._on_listener_gc)
            self._weak_listeners.append(weak_ref)
            return lambda: self._weak_listeners.remove(weak_ref)
        else:
            self._listeners.append(listener)
            return lambda: self._listeners.remove(listener)

    def _on_listener_gc(self, weak_ref):
        """Callback when weakly-referenced listener is garbage collected."""
        if weak_ref in self._weak_listeners:
            self._weak_listeners.remove(weak_ref)

    async def emit(
        self,
        event_type: str,
        data: Any,
        meta: Optional[Dict[str, Any]] = None
    ):
        """
        Publish an event.

        This implementation:
        1. Delivers directly to all listeners (original behavior)
        2. Also persists to DB via BaseStreamer (for backfill support)

        Args:
            event_type: Type of event (string or enum value)
            data: Event payload
            meta: Optional metadata
        """
        # Convert enum to string if needed
        from enum import Enum
        if isinstance(event_type, Enum):
            event_type = event_type.value

        # Create Event object
        event = Event(type=event_type, data=data, meta=meta)

        # 1. Deliver directly to listeners (original behavior, immediate)
        await self._deliver_to_listeners(event)

        # 2. Also persist via BaseStreamer (for DB backfill support)
        # This is done in background to not block
        if self._current_session_id is not None:
            try:
                streamer = self._ensure_streamer(self._current_session_id)
                # Fire-and-forget persistence
                asyncio.create_task(
                    streamer.emit(
                        event_type=event.type,
                        data=event.data,
                        **(event.meta or {})
                    )
                )
            except Exception as e:
                logger.error(f"Failed to persist event to DB: {e}", exc_info=e)

    def set_session_id(self, session_id: int):
        """Set current session ID for event emission."""
        self._current_session_id = session_id

    async def get_streamer(self, session_id: int) -> BaseStreamer:
        """
        Get BaseStreamer instance for direct access.

        Allows accessing advanced features like backfill and history sync.

        Args:
            session_id: The session ID

        Returns:
            BaseStreamer instance
        """
        return self._ensure_streamer(session_id)

    async def listen_stream(self, session_id: int, after_seq_id: int = -1):
        """
        Listen to events using BaseStreamer's backfill feature.

        This is a NEW API that provides backfill capability
        not available in the original EventManager.

        Args:
            session_id: The session ID
            after_seq_id: Only return events with seq_id > this value

        Yields:
            Event objects (converted from StreamerEvent)
        """
        streamer = self._ensure_streamer(session_id)
        async for streamer_event in streamer.listen(after_seq_id=after_seq_id):
            yield Event.from_streamer_event(streamer_event)

    async def sync_history(self, session_id: int):
        """
        Sync all events from history (no real-time listening).

        This is a NEW API that provides full history retrieval
        not available in the original EventManager.

        Args:
            session_id: The session ID

        Yields:
            Event objects (converted from StreamerEvent)
        """
        streamer = self._ensure_streamer(session_id)
        async for streamer_event in streamer.sync_history():
            yield Event.from_streamer_event(streamer_event)

    def clear(self):
        """Remove all listeners."""
        self._listeners.clear()
        self._weak_listeners.clear()
