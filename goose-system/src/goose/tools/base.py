"""
Tool Base

Tool 基类定义。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, TypeVar, Union
from enum import Enum
import uuid
import inspect

F = TypeVar('F', bound=Callable[..., Any])


class ToolCategory(str, Enum):
    """工具类别"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    SEARCH = "search"
    ANALYSIS = "analysis"
    UTILITY = "utility"


@dataclass
class Tool:
    """
    Tool 定义
    
    用于描述 Agent 可调用的工具。
    参考 OpenAI Function Calling 格式设计。
    """
    
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: ToolCategory = ToolCategory.UTILITY
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.parameters:
            self.parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
    
    @property
    def input_schema(self) -> Dict[str, Any]:
        """获取输入模式"""
        return self.parameters
    
    @property
    def required_parameters(self) -> List[str]:
        """获取必需参数列表"""
        return self.parameters.get("required", [])
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI 工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> tuple[bool, str]:
        """验证参数"""
        required = self.required_parameters
        for param in required:
            if param not in arguments:
                return False, f"Missing required parameter: {param}"
        
        return True, ""
    
    def __repr__(self) -> str:
        return f"Tool(name='{self.name}', description='{self.description[:50]}...')"


@dataclass
class ToolRequest:
    """工具调用请求"""
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    arguments: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolRequest":
        """从字典创建"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            arguments=data.get("arguments")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments or {}
        }


@dataclass
class ToolResponse:
    """工具调用响应"""
    tool_request_id: str
    success: bool = True
    content: Any = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_call_id": self.tool_request_id,
            "content": self.content,
            "success": self.success,
            "error": self.error
        }
    
    @classmethod
    def success_response(cls, tool_request_id: str, content: Any) -> "ToolResponse":
        """创建成功响应"""
        return cls(
            tool_request_id=tool_request_id,
            success=True,
            content=content
        )
    
    @classmethod
    def error_response(cls, tool_request_id: str, error: str) -> "ToolResponse":
        """创建错误响应"""
        return cls(
            tool_request_id=tool_request_id,
            success=False,
            error=error
        )


class FunctionTool(Tool):
    """
    函数式工具
    
    使用 Python 函数作为工具实现。
    支持通过 set_state() 注入运行时状态（如 shared_memory）。
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        function: Callable[..., Any],
        parameters: Optional[Dict[str, Any]] = None,
        requires_state: bool = False
    ):
        super().__init__(name, description, parameters or {})
        self.function = function
        self.category = ToolCategory.UTILITY
        self._state: Optional[Any] = None
        self.requires_state = requires_state
    
    def set_state(self, state: Any) -> None:
        """设置运行时状态"""
        self._state = state
    
    def clear_state(self) -> None:
        """清除运行时状态"""
        self._state = None
    
    async def execute(self, arguments: Dict[str, Any], state: Optional[Any] = None) -> Any:
        """
        执行工具
        
        Args:
            arguments: 参数
            state: 可选的运行时状态
        """
        import inspect
        sig = inspect.signature(self.function)
        
        valid_args = {}
        has_state_param = False
        for param_name, param in sig.parameters.items():
            if param_name == "_state":
                has_state_param = True
                if state is not None:
                    valid_args[param_name] = state
                elif self._state is not None:
                    valid_args[param_name] = self._state
            elif param_name in arguments:
                valid_args[param_name] = arguments[param_name]
        
        if has_state_param and state is not None:
            self._state = state
        
        if inspect.iscoroutinefunction(self.function):
            return await self.function(**valid_args)
        else:
            return self.function(**valid_args)


def create_tool_from_function(func: Callable[..., Any], name: Optional[str] = None) -> FunctionTool:
    """
    从 Python 函数创建工具
    
    Args:
        func: Python 函数
        name: 可选的名称
        
    Returns:
        FunctionTool: 创建的工具
    """
    import inspect
    
    name = name or func.__name__
    doc = inspect.getdoc(func) or ""
    
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        param_type = "string"
        if param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"
        elif param.annotation is bool:
            param_type = "boolean"
        
        properties[param_name] = {
            "type": param_type,
            "description": f"Parameter: {param_name}"
        }
        
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    
    parameters = {
        "type": "object",
        "properties": properties,
        "required": required
    }
    
    return FunctionTool(
        name=name,
        description=doc,
        function=func,
        parameters=parameters
    )


def tool_to_mcp_format(tool: Tool) -> Dict[str, Any]:
    """将 Tool 转换为 MCP 工具格式"""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters
    }


def function_tool_to_mcp_format(func_tool: FunctionTool) -> Dict[str, Any]:
    """将 FunctionTool 转换为 MCP 工具格式（包含完整参数定义）"""
    import inspect
    
    sig = inspect.signature(func_tool.function)
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        if param_name == "_state":
            continue
        
        param_type = "string"
        if param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"
        elif param.annotation is bool:
            param_type = "boolean"
        
        properties[param_name] = {
            "type": param_type,
            "description": f"Parameter: {param_name}"
        }
        
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    
    return {
        "name": func_tool.name,
        "description": func_tool.description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required
        }
    }
