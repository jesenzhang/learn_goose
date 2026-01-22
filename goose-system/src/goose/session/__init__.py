"""
Session Module Init

提供会话管理功能：
- SessionManager: 会话生命周期管理
- SessionState: 会话状态
- SharedStateManager: 跨会话共享状态
"""

from .manager import (
    SessionManager,
    SessionState,
    SessionMessage,
    SessionEvent,
    SessionEventType,
    SessionBackend,
    MemorySessionBackend,
    FileSessionBackend,
    SharedStateManager,
    create_session_manager,
)

__all__ = [
    "SessionManager",
    "SessionState",
    "SessionMessage",
    "SessionEvent",
    "SessionEventType",
    "SessionBackend",
    "MemorySessionBackend",
    "FileSessionBackend",
    "SharedStateManager",
    "create_session_manager",
]
