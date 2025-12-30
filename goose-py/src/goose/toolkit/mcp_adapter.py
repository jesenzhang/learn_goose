from typing import Any, Dict, Type, List
from pydantic import BaseModel, create_model, Field

from .base import Tool
from goose.conversation.message import CallToolResult, RawContent
from goose.mcp.client import McpClient, McpToolDef

class McpTool(Tool):
    """
    将 MCP 工具定义适配为 Goose 的 Tool 类。
    """
    def __init__(self, client: McpClient, tool_def: McpToolDef):
        self.client = client
        self.tool_def = tool_def
        
        # 设置基本属性
        self.name = tool_def.name
        self.description = tool_def.description
        
        # 动态生成 Pydantic 模型
        self.args_schema = self._build_pydantic_model(tool_def.input_schema)

    def _build_pydantic_model(self, schema: Dict[str, Any]) -> Type[BaseModel]:
        """
        根据 JSON Schema 动态创建 Pydantic 模型。
        注意：这是一个简化实现，处理基本的 string/int/bool/array。
        对于极度复杂的嵌套 Schema，可能需要更完善的转换逻辑。
        """
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))
        
        fields = {}
        
        for field_name, field_info in properties.items():
            field_type = str
            json_type = field_info.get("type", "string")
            
            if json_type == "integer": field_type = int
            elif json_type == "boolean": field_type = bool
            elif json_type == "number": field_type = float
            elif json_type == "array": field_type = List[Any] # 简化处理
            elif json_type == "object": field_type = Dict[str, Any]
            
            # 设置默认值
            if field_name in required_fields:
                default = ... # Pydantic 的 required 标记
            else:
                default = None
            
            fields[field_name] = (field_type, Field(
                default=default, 
                description=field_info.get("description", "")
            ))
        
        # 创建动态模型
        # model_name 必须唯一，防止注册表冲突
        model_name = f"{self.name}_Args"
        return create_model(model_name, **fields)

    async def run(self, **kwargs) -> CallToolResult:
        try:
            result = await self.client.call_tool(self.name, kwargs)
            
            contents = []
            is_error = result.get("isError", False)
            
            for item in result.get("content", []):
                if item.get("type") == "text":
                    contents.append(RawContent(type="text", text=item.get("text")))
                elif item.get("type") == "image":
                    contents.append(RawContent(
                        type="image", 
                        data=item.get("data"), 
                        mimeType=item.get("mimeType")
                    ))
            
            # [确认] 返回 CallToolResult
            return CallToolResult(content=contents, isError=is_error)

        except Exception as e:
            return CallToolResult.failure(f"MCP Execution Error: {str(e)}")