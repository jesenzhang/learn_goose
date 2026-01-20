"""
Unified Toolkit - Tool registration and management.

This module provides a unified interface for tool management across
different registration methods (decorator, skill, MCP, builtin).
"""
from typing import Dict, Any, Optional, Callable, Type

from .registry import (
    ToolRegistry,
    get_global_registry,
    register_tool,
    register_tool_class,
    tool_registry,
)
from .executor import (
    ExecutionStatus,
    ExecutionContext,
    ExecutionResult,
    ToolExecutor,
    get_global_executor,
    tool_executor,
    execute_tool
)

from .tool import (
    ToolSourceType,
    ToolDefinition,
    BaseTool
)

from .builtin import get_builtin_tool_names, get_builtin_tool
for tool_name in get_builtin_tool_names():
    t = get_builtin_tool(tool_name)
    register_tool_class(t.__class__)
    
__all__ = [
    # Registry
    "ToolSourceType",
    "ToolSourceType",  # Alias for ToolType
    "ToolDefinition",
    "ToolDefinition",  # Alias for ToolMetadata
    "ToolRegistry",

    "register_tool",
    "register_tool_class",
    
    "get_global_registry",
    "tool_registry",  # Global registry instance
    
    "get_global_executor",
    "tool_executor",

    # Executor
    "ExecutionStatus",
    "ExecutionContext",
    "ExecutionResult",
    "ToolExecutor",

]
