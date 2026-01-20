"""
Runtime Config - langgraph-style configuration for execution context.

This module provides a runtime configuration pattern following langgraph's
'configurable' approach for managing execution context parameters.
"""

from typing import Any, Dict, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

# Avoid circular import
if TYPE_CHECKING:
    from pho.toolkit.executor import ExecutionContext


class RuntimeConfig(BaseModel):
    """
    Runtime configuration following langgraph pattern.

    This corresponds to the 'config' parameter in langgraph with
    'configurable' key for user-defined execution parameters.

    Usage:
        config = RuntimeConfig(
            thread_id="session_123",
            user_id="user_456",
            user_role="admin",
            configurable={"max_retries": 3, "timeout": 30},
        )

        # Convert to toolkit.ExecutionContext
        ctx = config.to_execution_context()
    """

    # Core identifiers
    thread_id: str = Field(..., description="Thread/session ID")
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID (alias for thread_id)"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User ID"
    )
    user_role: Optional[str] = Field(
        default=None,
        description="User role (e.g., 'admin', 'user')"
    )

    # User-configurable parameters (langgraph configurable)
    configurable: Dict[str, Any] = Field(
        default_factory=dict,
        description="User-configurable execution parameters"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional execution metadata"
    )

    def to_execution_context(self) -> "ExecutionContext":
        """
        Convert to toolkit.ExecutionContext.

        Returns:
            ExecutionContext with session_id, user_id, and variables
        """
        # Import here to avoid circular dependency
        from pho.toolkit.executor import ExecutionContext

        return ExecutionContext(
            session_id=self.session_id or self.thread_id,
            user_id=self.user_id,
            user_role=self.user_role,
            variables=self.configurable.copy(),
        )

    @property
    def session_id_or_thread(self) -> str:
        """Get session_id or fallback to thread_id."""
        return self.session_id or self.thread_id

    @property
    def effective_user_id(self) -> str:
        """Get effective user_id, raise if not set."""
        if not self.user_id:
            raise ValueError("user_id is required but not set in RuntimeConfig")
        return self.user_id

    def set_configurable(self, key: str, value: Any) -> None:
        """Set a configurable parameter."""
        self.configurable[key] = value

    def get_configurable(self, key: str, default: Any = None) -> Any:
        """Get a configurable parameter."""
        return self.configurable.get(key, default)

    def update_configurable(self, updates: Dict[str, Any]) -> None:
        """Update multiple configurable parameters."""
        self.configurable.update(updates)


__all__ = [
    "RuntimeConfig",
]
