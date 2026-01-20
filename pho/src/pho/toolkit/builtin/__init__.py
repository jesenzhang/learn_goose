"""
Builtin tools for pho.

This module provides all 17 builtin tools from opencode-tool.
"""

from .bash import BashTool,BashParams
from .batch import BatchTool,BatchParams
from .codesearch import CodeSearchTool,CodeSearchParams
from .edit import EditTool,EditParams
from .glob import GlobTool,GlobParams
from .grep import GrepTool,GrepParams
from .ls import ListTool,ListParams
from .multiedit import MultiEditTool,MultiEditParams
from .plan import PlanEnterTool,PlanExitTool
from .read import ReadTool, ReadParams
from .write import WriteTool,WriteParams
from .skill import SkillTool,SkillParams
from .task import TaskTool,TaskParams
from .todo import TodoReadTool,TodoWriteTool,TodoReadParams,TodoWriteParams,TodoItem
from .webfetch import WebFetchTool,WebFetchParams
from .websearch import WebSearchTool,WebSearchParams

__all__ = [
   
    "BashTool",
    "BashParams", 
    
    "BatchTool",
    "BatchParams",
    
    "CodeSearchTool",
    "CodeSearchParams",
    
    "EditTool", 
    "EditParams",
    
    "GlobTool",
    "GlobParams",
    
    "GrepTool",
    "GrepParams",
    
    "ListTool",
    "ListParams",
    
    "MultiEditTool",
    "MultiEditParams",
    
    "PlanEnterTool",
    "PlanExitTool",
    
    "ReadTool",
    "ReadParams",
    
    "WriteTool",
    "WriteParams",
    
    "SkillTool",
    "SkillParams",
    
    "TaskTool",
    "TaskParams",
    
    "TodoReadTool",
    "TodoWriteTool",
    "TodoReadParams",
    "TodoWriteParams",
    "TodoItem",
      
    "WebFetchTool",
    "WebFetchParams",
    
    "WebSearchTool",
    "WebSearchParams",
]

# Add new functions here
_TOOL_CLASSES = {
    "bash": BashTool,
    "batch": BatchTool,
    "codesearch": CodeSearchTool,
    "edit": EditTool,
    "glob": GlobTool,
    "grep": GrepTool,
    "ls": ListTool,
    "multiedit": MultiEditTool,
    "plan_enter": PlanEnterTool,
    "plan_exit": PlanExitTool,
    "read": ReadTool,
    "write": WriteTool,
    "skill": SkillTool,
    "task": TaskTool,
    "todo_read": TodoReadTool,
    "todo_write": TodoWriteTool,
    "webfetch": WebFetchTool,
    "websearch": WebSearchTool,
}

def get_builtin_tool_names():
    """Get a list of all builtin tool names."""
    return list(_TOOL_CLASSES.keys())

def get_builtin_tool(name, config=None):
    """Get an instance of a builtin tool by name.
    
    Args:
        name: The name of the tool to instantiate
        config: Optional configuration for the tool
        
    Returns:
        An instance of the requested tool, or None if the tool doesn't exist
    """
    if name not in _TOOL_CLASSES:
        return None
    
    tool_class = _TOOL_CLASSES[name]
    return tool_class(config=config)
