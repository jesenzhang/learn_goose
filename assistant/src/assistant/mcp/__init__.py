"""
MCP (Model Context Protocol) Package.

This package provides MCP compatibility layer for Python tools,
following the same architecture as goose-rs.
"""

from .adapter import (
    MCPTool,
    register_builtin,
    get_builtin_tool,
    get_builtin_registry,
    list_builtin_tools,
    ErrorData,
    ErrorCode
)

from .builtin_tools import (
    get_builtin_tools_info,
    get_tool_instance,
    list_tool_names,
    # Tool classes
    ShellTool,
    WebScrapeTool,
    ReadFileTool,
    WriteFileTool,
    RememberMemoryTool,
    RetrieveMemoriesTool,
    ListDirectoryTool,
    SearchFilesTool,
)

__all__ = [
    # Core types
    "MCPTool",
    "register_builtin",
    "get_builtin_tool",
    "get_builtin_registry",
    "list_builtin_tools",
    "ErrorData",
    "ErrorCode",

    # Builtin tools
    "get_builtin_tools_info",
    "get_tool_instance",
    "list_tool_names",

    # Tool classes
    "ShellTool",
    "WebScrapeTool",
    "ReadFileTool",
    "WriteFileTool",
    "RememberMemoryTool",
    "RetrieveMemoriesTool",
    "ListDirectoryTool",
    "SearchFilesTool",
]
