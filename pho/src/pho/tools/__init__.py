"""
Pho Tools Module (deprecated - use toolkit instead).

This module is now deprecated. All tool registration and execution
should use the unified toolkit module instead.

For new code, use:
    from pho.toolkit import tool_registry, ToolExecutor

For compatibility, basic exports are still available:
    from pho.tools.tool import Tool, ToolResult, ToolError, ToolInfo
    from pho.tools.builtin import get_builtin_tool_class, get_builtin_tool_names
"""

# Export for backward compatibility
from .tool import (
    Tool,
    ToolError,
    ToolInfo,
    ToolResult,
    ToolState,
    ToolInputSchema,
    define_tool,
    InvalidTool,
)
from .builtin import (
    register_builtin_tools,
    get_builtin_tool_names,
    get_builtin_tool_class,
)

__all__ = [
    # Core classes
    "Tool",
    "ToolError",
    "ToolInfo",
    "ToolResult",
    "ToolState",
    "ToolInputSchema",
    "define_tool",
    "InvalidTool",
    # Builtin access
    "register_builtin_tools",
    "get_builtin_tool_names",
    "get_builtin_tool_class",
]
