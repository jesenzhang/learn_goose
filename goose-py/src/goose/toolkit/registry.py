import logging
import inspect
from typing import Dict, Callable, Any, Optional,List,Type,Union
from pydantic import BaseModel
from goose.registry import sys_registry,BaseRegistry,RegistryEntry
from .base import Tool 
from .protocol import ToolSourceType,ToolDefinition
from goose.utils.type_converter import TypeConverter
from goose.mcp.client import McpClient, McpToolDef
from .mcp_adapter import McpTool

logger = logging.getLogger("goose.toolkit.registry")


class ToolRegistry(BaseRegistry[Tool, ToolDefinition]):
    """
    [Domain Registry] 工具专用注册器
    Body: Tool (实例)
    Meta: ToolDefinition
    """
    
    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """
        导出为 OpenAI Chat Completion API 需要的 tools 格式
        """
        tools = []
        for entry in self.list_entries():
            meta = entry.meta
            tools.append({
                "type": "function",
                "function": {
                    "name": meta.name,
                    "description": meta.description,
                    "parameters": meta.args_schema  # 确保这是标准的 JSON Schema
                }
            })
        return tools
    
tool_registry = ToolRegistry('tools')

# --- 1. 简单的函数包装器 (Body) ---
class FunctionTool(Tool):
    def __init__(self, name: str, func: Callable, desc: str):
        self.name = name
        self.description = desc
        self.func = func
    
    async def run(self, **kwargs):
        # 支持异步和同步函数
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        return self.func(**kwargs)
    
 
# --- 2. 装饰器实现 ---
def register_tool(
    name: str = None,
    description: str = "",
    args_model: Type[BaseModel] = None # 可选：显式传入 Pydantic 模型
):
    """
    [Decorator] 注册 Python 函数为工具
    """
    def wrapper(obj: Union[Type[Tool], Callable]):
        # --- 情况 A: 装饰的是 Tool 子类 ---
        if inspect.isclass(obj) and issubclass(obj, Tool):
            # 1. Body: 实例化工具
            tool_instance = obj()
            
            # 2. Meta: 从类属性提取
            tool_name = name or tool_instance.name
            tool_desc = description or tool_instance.description
            
            # 提取 Pydantic Schema
            # 注意：args_schema 是 Pydantic Model Class
            json_schema = {}
            if tool_instance.args_schema:
                json_schema = tool_instance.args_schema.model_json_schema()
                # 清理 Pydantic 生成的额外 Title，保持 Schema 简洁
                json_schema.pop("title", None)

            meta = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                source_type=ToolSourceType.BUILTIN,
                args_schema=json_schema
            )
            
            # 3. 注册
            entry = RegistryEntry(id=tool_name, body=tool_instance, meta=meta)
            tool_registry.register(entry)
            
            return obj
        elif callable(obj):
            
            tool_name = name or obj.__name__
            tool_desc = description or obj.__doc__ or ""
            
            # A. 构建 Meta (ToolDefinition)
            # 如果没传 args_model，尝试自动推断
            if args_model:
                schema = args_model.model_json_schema()
            else:
                # TODO: 实现 inspect 推断逻辑，生成 JSON Schema
                # 这里简化处理，实际可以使用 Pydantic 的 validate_arguments 内部逻辑
                schema = TypeConverter.to_json_schema(TypeConverter.infer_input_schema(obj))

            meta = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                source_type=ToolSourceType.BUILTIN,
                args_schema=schema
            )
            
            # B. 构建 Body (Tool Instance)
            body = FunctionTool(tool_name, obj, tool_desc)
            
            # C. 注册到 SystemRegistry
            entry = RegistryEntry(id=tool_name, body=body, meta=meta)
            tool_registry.register(entry)
            
            return obj
        else:
            raise TypeError("@register_tool can only be used on functions or Tool subclasses")
        
    return wrapper



# ==========================================
# 3. 注册加载器 (The Loader)
# ==========================================

async def register_mcp_server(server_name: str, command: str, args: List[str] = []):
    """
    [Loader] 连接 MCP Server 并将所有工具注册到 SystemRegistry
    """
    # 1. 初始化并连接客户端
    client = McpClient(command, args)
    await client.connect()
    
    # 2. 获取工具列表 (Discovery)
    mcp_tools = await client.list_tools()
    
    logger.info(f"📦 Found {len(mcp_tools)} tools in MCP server '{server_name}'")

    for tool_info in mcp_tools:
        name = tool_info["name"]
        desc = tool_info.get("description", "")
        schema = tool_info.get("inputSchema", {})
        
        # 3. 构建 Meta (ToolDefinition)
        # 这里的 source_type 标记为 MCP，execution_config 可以存储 server 信息
        meta = ToolDefinition(
            id=name, # 或者加前缀 f"{server_name}__{name}" 防止冲突
            name=name,
            description=desc,
            source_type=ToolSourceType.MCP,
            args_schema=schema,
            execution_config={
                "server_name": server_name,
                "command": command
            }
        )
        
        # 4. 构建 Body (McpTool Instance)
        # 注意：这里我们将 client 实例注入到了工具中，保持连接复用
        body = McpTool(client, name, desc)
        
        # 5. 注册到 SystemRegistry
        tool_registry.register(
            RegistryEntry(id=name, body=body, meta=meta)
        )