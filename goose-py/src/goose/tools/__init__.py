from .base import Tool, ToolError
from .registry import ToolRegistry
from .builtins.shell import ShellTool
from .builtins.file import WriteFileTool, ReadFileTool
from .builtins.patch import PatchFileTool  # <--- 新增