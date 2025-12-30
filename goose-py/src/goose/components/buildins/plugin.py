import httpx
import asyncio
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from goose.components.base import Component
from goose.toolkit import tool_registry, ToolDefinition, ToolSourceType
from goose.utils.template import TemplateRenderer
from goose.components.registry import register_component
from goose.types import NodeTypes


# --- 配置模型 (保持对 Coze 协议的兼容) ---
class ApiParam(BaseModel):
    name: str
    value: Any # 可能是静态值，也可能是 {{var}}

class PluginConfig(BaseModel):
    # Coze 风格配置：通过 key-value 列表传递参数
    apiParam: List[ApiParam] = Field(default_factory=list)
    
    # 错误处理配置 (可选)
    settingOnError: Optional[Dict[str, Any]] = None
    
    # 为了方便 Goose 原生使用，允许直接指定 tool_id
    tool_id: Optional[str] = None

@register_component(
    name=NodeTypes.PLUGIN,
    group="Tool",
    label="插件/工具执行器",
    description="执行 HTTP 插件、本地函数或子工作流",
    icon="zap",
    author="System",
    version="1.0.0",
    config_model=PluginConfig
)
class PluginComponent(Component):
    async def execute(self, inputs: Dict[str, Any], config: PluginConfig) -> Dict[str, Any]:
        
        # 1. [解析] 确定 Tool ID
        tool_id = config.tool_id
        if not tool_id:
            tool_id = self._extract_tool_id(config.apiParam)
        
        if not tool_id:
            raise ValueError("Plugin configuration missing 'tool_id'")

        # 2. [查找] 从注册表获取工具定义
        tool_def = tool_registry.get(tool_id)
        if not tool_def:
            raise ValueError(f"Tool definition not found for ID: {tool_id}")

        print(f" 🔌 [Plugin] Executing: {tool_def.name} ({tool_def.source_type})")

        # 3. [参数准备]
        # 将 apiParam 列表转换为字典，并渲染变量
        # 优先级：inputs (直接传入) > apiParam (配置默认值/映射)
        tool_inputs = self._prepare_tool_inputs(config.apiParam, inputs)

        # 4. [分发执行]
        try:
            if tool_def.source_type == ToolSourceType.PLUGIN:
                return await self._run_http_plugin(tool_def, tool_inputs)

            elif tool_def.source_type == ToolSourceType.BUILTIN:
                return await self._run_builtin_function(tool_def, tool_inputs)

            elif tool_def.source_type == ToolSourceType.WORKFLOW:
                # 注意：execute 方法的第一个参数 component 自身通常无法直接拿到 ctx
                # 但 Goose 的 Component.execute 签名是 (self, inputs, config)
                # 为了拿到 ctx (WorkflowContext) 来运行子工作流，我们需要稍微 hack 一下
                # 或者假设调用方在 inputs 里注入了 ctx (不推荐)
                # 正确做法：修改 Component.execute 签名接收 context，或者在此处依赖外部注入
                
                # 这里假设 Component 基类或调用机制允许访问上下文，暂且留空或模拟
                # 如果 Goose 架构支持 run_sub_workflow，通常是在 Scheduler 层面
                # 这里演示如何抛出请求给 Scheduler (参考 Control 组件的协议)
                return await self._run_workflow_tool(tool_def, tool_inputs)

            else:
                raise ValueError(f"Unknown source type: {tool_def.source_type}")

        except Exception as e:
            # 错误处理策略
            if config.settingOnError and config.settingOnError.get("processType") == 2:
                return {"error": str(e), "status": "ignored"}
            raise e

    def _extract_tool_id(self, api_params: List[ApiParam]) -> Optional[str]:
        for param in api_params:
            if param.name in ["tool_id", "api_name", "__id"]:
                return str(param.value)
        return None

    def _prepare_tool_inputs(self, api_params: List[ApiParam], runtime_inputs: Dict) -> Dict:
        """合并配置参数和运行时参数"""
        final_inputs = runtime_inputs.copy()
        
        for param in api_params:
            # 跳过元数据 key
            if param.name in ["tool_id", "api_name", "__id"]:
                continue
            
            # 如果运行时没有传这个参数，则使用配置中的值 (支持渲染)
            if param.name not in final_inputs:
                val = param.value
                if isinstance(val, str):
                    val = TemplateRenderer.render(val, runtime_inputs)
                final_inputs[param.name] = val
                
        return final_inputs

    # --- Executors ---

    async def _run_http_plugin(self, tool_def: ToolDefinition, inputs: Dict) -> Dict:
        conf = tool_def.execution_config or {}
        url = conf.get("url")
        method = conf.get("method", "GET").upper()
        
        if not url:
            raise ValueError(f"Plugin {tool_def.name} missing URL configuration")

        # 简化的 Auth 处理
        auth = conf.get("auth", {})
        headers = {}
        query_params = {}
        
        if auth.get("type") == "bearer":
            headers["Authorization"] = f"Bearer {auth.get('token')}"
        elif auth.get("type") == "api_key":
            k = auth.get("key", "Authorization")
            v = auth.get("value", "")
            if auth.get("in") == "query":
                query_params[k] = v
            else:
                headers[k] = v

        # 发起请求
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                final_params = {**inputs, **query_params}
                resp = await client.get(url, params=final_params, headers=headers)
            else:
                resp = await client.request(method, url, json=inputs, params=query_params, headers=headers)
            
            resp.raise_for_status()
            try:
                return resp.json()
            except:
                return {"text": resp.text}

    async def _run_builtin_function(self, tool_def: ToolDefinition, inputs: Dict) -> Dict:
        func = tool_def.func
        if not func:
            raise ValueError(f"Builtin tool {tool_def.name} missing implementation")

        import inspect
        if inspect.iscoroutinefunction(func):
            result = await func(**inputs)
        else:
            result = await asyncio.to_thread(func, **inputs)
            
        if isinstance(result, dict): return result
        return {"output": result}

    async def _run_workflow_tool(self, tool_def: ToolDefinition, inputs: Dict) -> Dict:
        """
        调用子工作流。
        注意：这通常需要 Scheduler 的支持。
        Goose 的组件 execute 签名目前不包含 ctx，
        如果您按照之前的建议修改了 Component.invoke 传入 context，这里就可以使用了。
        """
        # 假设 execute 能够访问上下文 (这里伪代码演示)
        # ctx = self.context 
        # return await ctx.executor.run_sub_workflow(...)
        
        # 临时方案：返回特殊信号，让 Scheduler 接管 (类似于 Control 组件的设计)
        return {
            "_control_signal": "SUB_WORKFLOW",
            "workflow_id": tool_def.workflow_id,
            "inputs": inputs
        }