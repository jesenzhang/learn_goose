"""
Unified Toolkit - Tool registration and management.

This module provides a unified interface for tool management across
different registration methods (decorator, skill, MCP).
"""

from .registry import (
    ToolType,
    ToolMetadata,
    ToolRegistry,
    get_global_registry,
    register_tool,
)
from .executor import (
    ExecutionStatus,
    ExecutionContext,
    ExecutionResult,
    ToolExecutor,
)

# Global registry instance for convenient access
tool_registry = get_global_registry()

# Alias for compatibility with legacy code
ToolSourceType = ToolType
ToolDefinition = ToolMetadata

__all__ = [
    # Registry
    "ToolType",
    "ToolSourceType",  # Alias for ToolType
    "ToolMetadata",
    "ToolDefinition",  # Alias for ToolMetadata
    "ToolRegistry",
    "get_global_registry",
    "tool_registry",  # Global registry instance
    "register_tool",

    # Executor
    "ExecutionStatus",
    "ExecutionContext",
    "ExecutionResult",
    "ToolExecutor",
]
