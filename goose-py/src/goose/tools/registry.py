import logging
from typing import Dict, Callable, Any, Optional,List
from pydantic import BaseModel

# 假设这是您现有的 Tool 定义
from .base import Tool 

logger = logging.getLogger("goose.tools.registry")

class ToolRegistry:
    """
    工具注册中心 (Singleton)
    负责存储: Tool ID -> Tool Runtime Object
    """
    _tools: Dict[str, Tool] = {}

    @classmethod
    def register(cls, name: str = None, description: str = ""):
        """
        装饰器：注册一个 Python 函数为工具
        @ToolRegistry.register(name="google_search")
        def google_search(query: str): ...
        """
        def decorator(func: Callable):
            tool_name = name or func.__name__
            # 将函数包装为 Goose 的 Tool 对象
            tool_instance = Tool(
                name=tool_name,
                func=func,
                description=description or func.__doc__ or ""
            )
            cls._tools[tool_name] = tool_instance
            logger.info(f"🛠️ Registered Tool: {tool_name}")
            return func
        return decorator

    @classmethod
    def register_instance(cls, tool: Tool):
        """直接注册已有的 Tool 实例"""
        if tool.name in cls._tools:
            logger.warning(f"Overwriting tool: {tool.name}")
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Optional[Tool]:
        """根据 ID 获取工具"""
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls):
        """导出给前端选择工具列表"""
        return [
            {"name": t.name, "description": t.description, "schema": t.to_schema()}
            for t in cls._tools.values()
        ]
        
    def list_definitions(self) -> List[Dict]:
        """返回所有工具的 Schema 定义列表"""
        return [t.to_openai_tool() for t in self._tools.values()]

# 快捷方式
register_tool = ToolRegistry.register