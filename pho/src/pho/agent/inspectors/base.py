"""
Tool Inspector Chain - Base classes for tool inspection.

The inspector chain is inspired by goose-rs and provides a way to inspect
and validate tool calls before execution.

Inspectors can:
- Validate tool arguments
- Check permissions
- Detect security issues
- Prevent repetitive calls
- Modify tool arguments
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class InspectorAction(str, Enum):
    """Action to take after inspection"""
    ALLOW = "allow"              # Allow tool call to proceed
    DENY = "deny"                # Block tool call
    MODIFY = "modify"            # Modify arguments before execution
    REPLACE = "replace"          # Replace with different tool/result


class InspectorResult:
    """Result of tool inspection"""

    def __init__(
        self,
        action: InspectorAction,
        reason: Optional[str] = None,
        modified_args: Optional[Dict[str, Any]] = None,
        replacement_result: Optional[Any] = None,
        error_message: Optional[str] = None
    ):
        self.action = action
        self.reason = reason
        self.modified_args = modified_args
        self.replacement_result = replacement_result
        self.error_message = error_message

    def is_allowed(self) -> bool:
        return self.action == InspectorAction.ALLOW

    def is_denied(self) -> bool:
        return self.action == InspectorAction.DENY

    def is_modified(self) -> bool:
        return self.action == InspectorAction.MODIFY

    def is_replaced(self) -> bool:
        return self.action == InspectorAction.REPLACE

    @classmethod
    def allow(cls, reason: Optional[str] = None) -> "InspectorResult":
        return cls(action=InspectorAction.ALLOW, reason=reason)

    @classmethod
    def deny(cls, reason: str, error_message: Optional[str] = None) -> "InspectorResult":
        return cls(
            action=InspectorAction.DENY,
            reason=reason,
            error_message=error_message or reason
        )

    @classmethod
    def modify(cls, args: Dict[str, Any], reason: Optional[str] = None) -> "InspectorResult":
        return cls(
            action=InspectorAction.MODIFY,
            reason=reason,
            modified_args=args
        )

    @classmethod
    def replace(cls, result: Any, reason: Optional[str] = None) -> "InspectorResult":
        return cls(
            action=InspectorAction.REPLACE,
            reason=reason,
            replacement_result=result
        )


class ToolInspector(ABC):
    """
    Base class for tool inspectors.

    Inspectors are called before tool execution to validate,
    check permissions, detect issues, or modify arguments.

    The inspector chain processes tool calls in order.
    If any inspector denies, the call is blocked.
    """

    def __init__(self, priority: int = 0):
        """
        Initialize inspector.

        Args:
            priority: Lower values execute first (default 0)
        """
        self.priority = priority
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """Enable this inspector"""
        self._enabled = True

    def disable(self) -> None:
        """Disable this inspector"""
        self._enabled = False

    @abstractmethod
    async def inspect(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> InspectorResult:
        """
        Inspect a tool call before execution.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool
            context: Additional context (user_id, session_id, etc.)

        Returns:
            InspectorResult with action to take
        """
        pass

    async def after_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Hook called after tool execution.

        Can be used to track call history, collect statistics, etc.

        Args:
            tool_name: Name of the tool that was called
            tool_args: Arguments passed to the tool
            result: Result returned by the tool
            context: Additional context
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(priority={self.priority}, enabled={self._enabled})"


class InspectorChain:
    """
    Chain of tool inspectors.

    Inspectors are executed in priority order (lower values first).
    The chain stops at the first DENY action.
    MODIFY actions can be chained (each inspector sees modified args).
    """

    def __init__(self, inspectors: Optional[List[ToolInspector]] = None):
        """
        Initialize inspector chain.

        Args:
            inspectors: List of inspectors (will be sorted by priority)
        """
        self.inspectors: List[ToolInspector] = []
        if inspectors:
            self.add_inspectors(inspectors)

    def add_inspector(self, inspector: ToolInspector) -> None:
        """Add an inspector to the chain"""
        self.inspectors.append(inspector)
        self.inspectors.sort(key=lambda i: i.priority)

    def add_inspectors(self, inspectors: List[ToolInspector]) -> None:
        """Add multiple inspectors to the chain"""
        self.inspectors.extend(inspectors)
        self.inspectors.sort(key=lambda i: i.priority)

    def remove_inspector(self, inspector: ToolInspector) -> bool:
        """Remove an inspector from the chain"""
        if inspector in self.inspectors:
            self.inspectors.remove(inspector)
            return True
        return False

    def remove_inspectors_of_type(self, inspector_type: type) -> int:
        """Remove all inspectors of a given type"""
        before = len(self.inspectors)
        self.inspectors = [i for i in self.inspectors if not isinstance(i, inspector_type)]
        return before - len(self.inspectors)

    def get_inspectors_of_type(self, inspector_type: type) -> List[ToolInspector]:
        """Get all inspectors of a given type"""
        return [i for i in self.inspectors if isinstance(i, inspector_type)]

    async def inspect(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> InspectorResult:
        """
        Run all enabled inspectors in the chain.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool
            context: Additional context

        Returns:
            InspectorResult from the first denying inspector,
            or the last result if all pass/modify
        """
        current_args = tool_args
        final_result = InspectorResult.allow()

        for inspector in self.inspectors:
            if not inspector.enabled:
                continue

            try:
                result = await inspector.inspect(tool_name, current_args, context)

                # Stop on deny
                if result.is_denied():
                    logger.debug(
                        f"Inspector {inspector.__class__.__name__} denied "
                        f"tool '{tool_name}': {result.reason}"
                    )
                    return result

                # Update args if modified
                if result.is_modified():
                    current_args = result.modified_args
                    final_result = result
                    logger.debug(
                        f"Inspector {inspector.__class__.__name__} modified "
                        f"args for '{tool_name}': {result.reason}"
                    )

                # Return replacement immediately
                if result.is_replaced():
                    logger.debug(
                        f"Inspector {inspector.__class__.__name__} replaced "
                        f"tool '{tool_name}': {result.reason}"
                    )
                    return result

                # Update final result if allowed
                if result.is_allowed():
                    final_result = result

            except Exception as e:
                logger.error(f"Inspector {inspector.__class__.__name__} failed: {e}")
                # Continue to next inspector on error

        return final_result

    async def after_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Call after_call hook on all enabled inspectors"""
        for inspector in self.inspectors:
            if not inspector.enabled:
                continue

            try:
                await inspector.after_call(tool_name, tool_args, result, context)
            except Exception as e:
                logger.error(f"After-call hook failed for {inspector.__class__.__name__}: {e}")

    def __len__(self) -> int:
        return len(self.inspectors)

    def __repr__(self) -> str:
        return f"InspectorChain({len(self)} inspectors: {[i.__class__.__name__ for i in self.inspectors]})"


__all__ = [
    "InspectorAction",
    "InspectorResult",
    "ToolInspector",
    "InspectorChain",
]
