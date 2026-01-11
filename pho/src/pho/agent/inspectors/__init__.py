"""
Tool Inspector Chain - Security and validation for tool execution.

This module provides inspector classes that validate tool calls before execution.
Inspired by the goose-rs inspector chain pattern.
"""

from .base import (
    InspectorAction,
    InspectorResult,
    ToolInspector,
    InspectorChain,
)
from .security import SecurityInspector
from .permission import PermissionInspector, Permission, Role
from .repetition import RepetitionInspector, CallSignature, CallRecord

__all__ = [
    # Base
    "InspectorAction",
    "InspectorResult",
    "ToolInspector",
    "InspectorChain",

    # Inspectors
    "SecurityInspector",
    "PermissionInspector",
    "RepetitionInspector",

    # Supporting types
    "Permission",
    "Role",
    "CallSignature",
    "CallRecord",
]
