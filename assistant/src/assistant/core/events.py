"""
Event Bus Module - Event-driven core for agent system.

This module now imports from unified events package.
All existing code using this module will continue to work without changes.
"""

# Re-export from events package for backward compatibility
from ..events import EventManager, EventType, Event

__all__ = ["EventManager", "EventType", "Event"]
