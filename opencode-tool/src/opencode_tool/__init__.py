"""
opencode-tool - Python implementation of OpenCode Agent Tools

This package provides Python implementations of all the built-in tools
from the OpenCode Agent system, including:
- File operations (read, write, edit, glob, grep, ls)
- Bash command execution
- Web operations (websearch, webfetch)
- Task management (todo, task)
- Agent management (skill, batch, multiedit, plan)
- Code search (codesearch)
"""

from .tool import (
    Tool,
    ToolError,
    ToolInfo,
    ToolResult,
    ToolState,
)
from .registry import (
    ToolRegistry,
    get_registry,
    register_tool,
)

__version__ = "0.1.0"
__all__ = [
    "Tool",
    "ToolError",
    "ToolInfo",
    "ToolResult",
    "ToolState",
    "ToolRegistry",
    "get_registry",
    "register_tool",
]
