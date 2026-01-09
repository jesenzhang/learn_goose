"""
Event Bus Module - Event-driven core for agent system.

This module provides an event-driven architecture that decouples "what happens"
from "how it's transmitted", enabling real-time streaming responses.
"""

import logging
from enum import Enum
from typing import Any, Callable, Awaitable, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio
import weakref

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Event types for agent lifecycle and tool execution."""
    TOKEN = "token"                 # Streaming text tokens
    TOOL_START = "tool_start"       # Tool execution started
    TOOL_END = "tool_end"           # Tool execution completed
    TOOL_ARTIFACT = "tool_artifact" # Tool produced structured data (charts, tables)
    STATE_CHANGE = "state_change"   # Agent state changed (Intent/Plan)
    APPROVAL_REQ = "approval_req"   # Human approval required
    ERROR = "error"                 # Error occurred


class Event(BaseModel):
    """Immutable event representation."""
    type: EventType
    data: Any
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


class EventManager:
    """
    Asynchronous event manager with listener support.

    Features:
    - Subscription-based event publishing
    - Weak reference support to prevent memory leaks
    - Async listener execution
    """

    def __init__(self):
        self._listeners: List[Callable[[Event], Awaitable[None]]] = []
        self._weak_listeners: List[weakref.ref] = []

    def subscribe(self, listener: Callable[[Event], Awaitable[None]], weak: bool = False) -> Callable[[], None]:
        """
        Subscribe to events.

        Args:
            listener: Async callback that receives Event objects
            weak: If True, use weak reference to allow garbage collection

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

    async def emit(self, event_type: EventType, data: Any):
        """
        Publish an event to all listeners.

        Args:
            event_type: Type of event to emit
            data: Event payload
        """
        event = Event(type=event_type, data=data)

        # Collect all active listeners
        active_listeners = list(self._listeners)
        for weak_ref in self._weak_listeners:
            listener = weak_ref()
            if listener is not None:
                active_listeners.append(listener)

        # Execute all listeners concurrently
        if active_listeners:
            tasks = [listener(event) for listener in active_listeners]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log listener errors without crashing
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Event listener error: {result}", exc_info=result)

    def clear(self):
        """Remove all listeners. Useful for testing or cleanup."""
        self._listeners.clear()
        self._weak_listeners.clear()
