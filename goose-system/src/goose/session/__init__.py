"""
Session Module

Session state management with persistence support.
Reference: goose-rs session module

Features:
- SessionManager: Session lifecycle management with persistence
- Session: Session data structure with provider/model config, extension state
- SessionType: User/SubAgent/Scheduler/Workflow session types
"""

from .types import SessionType, Session, TokenStats, ExtensionData
from .manager import SessionManager


__all__ = [
    "SessionType",
    "Session",
    "SessionManager",
    "TokenStats",
    "ExtensionData",
]
