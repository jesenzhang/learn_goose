"""
Hook Models - Data structures for hook system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class HookAction(str, Enum):
    """Hook execution action types."""
    CONTINUE = "continue"      # Continue with next hook
    INTERCEPT = "intercept"     # Intercept and return response
    MODIFY = "modify"           # Modify data and continue
    SKIP = "skip"               # Skip current step
    RETRY = "retry"             # Retry current operation


@dataclass
class HookResult:
    """Result of a hook execution."""
    action: HookAction = HookAction.CONTINUE
    response: Optional[str] = None
    response_data: Optional[Any] = None
    modified_input: Optional[str] = None
    modified_data: Optional[Dict[str, Any]] = None
    retry_after: Optional[float] = None
    retry_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    immediate: bool = True

    @classmethod
    def continue_(cls) -> "HookResult":
        """Continue with next hook."""
        return cls(action=HookAction.CONTINUE)

    @classmethod
    def intercept(cls, response: str, response_data: Any = None) -> "HookResult":
        """Intercept and return response."""
        return cls(
            action=HookAction.INTERCEPT,
            response=response,
            response_data=response_data
        )

    @classmethod
    def modify_input(cls, new_input: str) -> "HookResult":
        """Modify input."""
        return cls(
            action=HookAction.MODIFY,
            modified_input=new_input
        )

    @classmethod
    def modify_data(cls, data: Dict[str, Any]) -> "HookResult":
        """Modify data."""
        return cls(
            action=HookAction.MODIFY,
            modified_data=data
        )

    @classmethod
    def skip(cls) -> "HookResult":
        """Skip current step."""
        return cls(action=HookAction.SKIP)

    @classmethod
    def retry(cls, reason: str, delay: float = 0) -> "HookResult":
        """Retry."""
        return cls(
            action=HookAction.RETRY,
            retry_reason=reason,
            retry_after=delay
        )

    @property
    def is_final(self) -> bool:
        """Whether this terminates the flow."""
        return self.action in (HookAction.INTERCEPT, HookAction.SKIP)

    @property
    def should_modify(self) -> bool:
        """Whether to modify data."""
        return self.action == HookAction.MODIFY


@dataclass
class HookContext:
    """Context for hook execution."""
    user_input: str
    session_id: str
    user_id: Optional[str] = None
    shared_data: Dict[str, Any] = field(default_factory=dict)
    executed_hooks: List[str] = field(default_factory=list)
    skipped_hooks: List[str] = field(default_factory=list)

    def get_shared(self, key: str, default: Any = None) -> Any:
        """Get shared data."""
        return self.shared_data.get(key, default)

    def set_shared(self, key: str, value: Any) -> None:
        """Set shared data."""
        self.shared_data[key] = value

    def mark_executed(self, hook_name: str) -> None:
        """Mark hook as executed."""
        self.executed_hooks.append(hook_name)

    def mark_skipped(self, hook_name: str, reason: str = "") -> None:
        """Mark hook as skipped."""
        self.skipped_hooks.append(f"{hook_name}:{reason}")


@dataclass
class HookConfig:
    """Hook configuration."""
    name: str
    enabled: bool = True
    priority: int = 100
    hook_type: str = "filter"  # filter, transformer, observer, validator
    conditions: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    fail_on_error: bool = False
    error_message: Optional[str] = None
