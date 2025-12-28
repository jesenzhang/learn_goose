import inspect
from abc import ABC, abstractmethod
from typing import Any, Dict, Type, Optional, Callable, Awaitable
from pydantic import BaseModel, Field, create_model

from ..conversation.message import CallToolResult, RawContent

class ToolError(Exception):
    """工具执行期间发生的错误"""
    pass

class Tool(ABC):
    """
    工具基类。
    所有 Goose 工具都应该继承此类。
    """
    name: str
    description: str
    args_schema: Type[BaseModel]

    def __init__(self):
        # 确保子类定义了必要的元数据
        if not hasattr(self, 'name') or not self.name:
            raise ValueError(f"Tool {self.__class__.__name__} must have a name")
        if not hasattr(self, 'description') or not self.description:
            raise ValueError(f"Tool {self.__class__.__name__} must have a description")
        if not hasattr(self, 'args_schema') or not issubclass(self.args_schema, BaseModel):
            raise ValueError(f"Tool {self.__class__.__name__} must define args_schema as a Pydantic model")

    @abstractmethod
    async def run(self, **kwargs) -> CallToolResult:
        """
        执行工具逻辑。
        必须返回 CallToolResult (包含 content 列表)
        """
        pass

    def to_schema(self) -> Dict[str, Any]:
        """
        转换为 OpenAI/Anthropic 兼容的 Function Schema
        """
        schema = self.args_schema.model_json_schema()
        
        # 清理 Pydantic 生成的额外字段，使其更符合 OpenAI 标准
        if "title" in schema:
            del schema["title"]
        
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": { # Goose/MCP 使用 input_schema, OpenAI 使用 parameters
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", [])
            }
        }

    # 兼容 OpenAI 格式
    def to_openai_tool(self) -> Dict[str, Any]:
        schema = self.to_schema()
        return {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["input_schema"]
            }
        }

# 简单的装饰器，用于快速定义函数工具
def tool(name: str, description: str, args_model: Type[BaseModel]):
    def decorator(func: Callable[..., Awaitable[CallToolResult]]):
        class DynamicTool(Tool):
            def __init__(self):
                self.name = name
                self.description = description
                self.args_schema = args_model
                super().__init__()

            async def run(self, **kwargs):
                return await func(**kwargs)
        
        return DynamicTool()
    return decorator