"""
Tool System

Tools for Goose-System agent.
"""

from .base import (
    Tool,
    ToolRequest,
    ToolResponse,
    ToolCategory,
    FunctionTool,
    create_tool_from_function,
    tool_to_mcp_format,
    function_tool_to_mcp_format,
)
from .executor import ToolExecutor, SyncToolExecutor
from .inspection import (
    ToolInspector,
    InspectionManager,
    InspectionResult,
    InspectionAction,
    SecurityInspector,
    PermissionInspector,
    PermissionStore,
    PermissionLevel,
    RepetitionInspector,
)
from .builtin import (
    create_builtin_tools,
    register_builtin_tools,
    read_file,
    write_file,
    edit_file,
    glob_files,
    grep_files,
    list_dir,
    run_bash,
)
from .code_mode import (
    CodeModeExecutor,
    CodeExecutionResult,
    DiscoveredTool,
    CodeModeAgent,
)

__all__ = [
    "Tool",
    "ToolRequest",
    "ToolResponse",
    "ToolCategory",
    "FunctionTool",
    "create_tool_from_function",
    "tool_to_mcp_format",
    "function_tool_to_mcp_format",
    "ToolExecutor",
    "SyncToolExecutor",
    "ToolInspector",
    "InspectionManager",
    "InspectionResult",
    "InspectionAction",
    "SecurityInspector",
    "PermissionInspector",
    "PermissionStore",
    "PermissionLevel",
    "RepetitionInspector",
    # Builtin tools
    "create_builtin_tools",
    "register_builtin_tools",
    "read_file",
    "write_file",
    "edit_file",
    "glob_files",
    "grep_files",
    "list_dir",
    "run_bash",
    # Code Mode
    "CodeModeExecutor",
    "CodeExecutionResult",
    "DiscoveredTool",
    "CodeModeAgent",
]
