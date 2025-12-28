from typing import Dict, List, Optional
from .base import Tool

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        if tool.name in self._tools:
            # 允许覆盖，或者抛出警告
            pass
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def list_definitions(self) -> List[Dict]:
        """返回所有工具的 Schema 定义列表"""
        return [t.to_openai_tool() for t in self._tools.values()]

# 全局单例（可选，也可以每个 Agent 一个 Registry）
global_registry = ToolRegistry()