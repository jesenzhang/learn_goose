import json
import re
import logging
import resource
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from goose.component.base import Component
from goose.component.registry import register_component
from goose.resources.tool import ToolDefinitionRegistry, ToolSourceType, ToolDefinition
from goose.workflow.context import WorkflowContext
from goose.utils.template import TemplateRenderer
from goose.providers import ProviderFactory
from goose.conversation import Message

logger = logging.getLogger("goose.component.llm")

# ==========================================
# 配置模型 (Schema Definition)
# ==========================================

class OutputDefinition(BaseModel):
    name: str
    type: str = "string" # string, number, boolean, array, object
    description: Optional[str] = None

class LLMConfig(BaseModel):
    # --- 模型配置 ---
    model: str = Field(..., description="模型名称 (e.g. gpt-4o)")
    base_url: Optional[str] = Field(None, description="API Base URL")
    api_key: Optional[str] = Field(None, description="API Key")
    
    # --- 提示词 ---
    prompt: str = Field(..., description="用户提示词 (支持 {{var}})")
    system_prompt: str = Field("", description="系统提示词 (支持 {{var}})")
    
    # --- 工具与参数 ---
    tools: List[str] = Field(default_factory=list, description="挂载的工具 ID 列表")
    
    # --- 输出控制 ---
    response_format: str = Field("text", description="输出模式: text 或 json_object")
    output_definitions: List[OutputDefinition] = Field(default_factory=list, description="输出变量定义")
    
    # --- 高级参数 ---
    temperature: float = 0.7
    max_tokens: int = 4096
    max_iterations: int = 5  # ReAct 最大循环次数
    
    model_config = ConfigDict(extra='allow')

# ==========================================
# LLM Component Implementation
# ==========================================

@register_component
class LLMComponent(Component):
    name = "llm"
    label = "大语言模型"
    description = "执行对话、工具调用及结构化输出"
    group = "AI"
    icon = "cpu"
    config_model = LLMConfig

    async def execute(self, inputs: Dict[str, Any],config: LLMConfig) -> Dict[str, Any]:
        """
        核心执行逻辑：
        1. 准备工具和模型。
        2. 渲染 Prompt。
        3. 注入 JSON Schema (如果需要)。
        4. 执行 ReAct 循环 (Chat -> Tool -> Chat)。
        5. 解析输出。
        """
        
        # 1. [准备] 工具定义
        tool_defs = []
        openai_tools = []
        
        if config.tools:
            for tool_id in config.tools:
                # 从 Goose 的 ToolRegistry 获取
                t_def = ToolDefinitionRegistry.get(tool_id)
                if t_def:
                    tool_defs.append(t_def)
                    # 转换为 OpenAI 格式 (假设 ToolDefinition 实现了 to_openai_format)
                    # 如果没有实现，这里需要手动转换，下文会提供 Helper
                    openai_tools.append(self._to_openai_tool(t_def))
                else:
                    logger.warning(f"Tool not found: {tool_id}")

        # 2. [准备] 模型 Provider
        # 优先使用 config 中的配置，如果没有则尝试从系统默认配置获取
        # 这里为了演示，每次创建一个临时的 Provider 实例
        provider_config = {
            "model_name": config.model,
            "api_key": config.api_key or "default", # 实际应从 ENV 或 KeyManager 获取
            "base_url": config.base_url,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens
        }
        # 简单工厂模式创建 Provider (OpenAI Compatible)
        provider = ProviderFactory.create("openai", provider_config)

        # 3. [渲染] Prompt
        system_instruction = config.system_prompt
        
        # 如果是 JSON 模式，构建 Schema 并注入 System Prompt
        if config.response_format == "json_object" and config.output_definitions:
            try:
                target_schema = self._build_json_schema(config.output_definitions)
                json_instruction = f"""
                \n\n## Output Requirement
                You MUST respond with a valid JSON object strictly adhering to the following Schema.
                Output raw JSON only. Do not use Markdown blocks.
                
                JSON Schema:
                {json.dumps(target_schema, indent=2)}
                """
                system_instruction += json_instruction
            except Exception as e:
                logger.warning(f"Failed to build JSON schema: {e}")

        # 使用 TemplateRenderer 渲染变量
        system_content = TemplateRenderer.render(system_instruction, inputs)
        user_content = TemplateRenderer.render(config.prompt, inputs)
        
        messages = []
        if system_content:
            messages.append(Message.system(system_content))
        messages.append(Message.user(user_content))

        # 4. [执行] ReAct Loop
        current_iter = 0
        final_response_content = ""
        final_reasoning_content = ""
        
        while current_iter < config.max_iterations:
            current_iter += 1
            
            # --- 调用 LLM ---
            # 注意：Goose 的 Provider 接口通常返回 Message 对象
            response_msg = await provider.generate(messages, tools=openai_tools if openai_tools else None)
            
            # 累积推理内容 (DeepSeek/O1)
            if response_msg.reasoning_content:
                final_reasoning_content += response_msg.reasoning_content
            
            # 追加到历史
            messages.append(response_msg)
            
            # 检查是否有工具调用
            if not response_msg.tool_calls:
                # 没有工具调用，任务结束
                final_response_content = response_msg.content
                break
            
            # --- 执行工具 ---
            logger.info(f"🔧 Tool Calls detected: {len(response_msg.tool_calls)}")
            
            for tool_call in response_msg.tool_calls:
                call_id = tool_call.id
                func_name = tool_call.function.name
                args_str = tool_call.function.arguments
                
                tool_result_content = ""
                
                # 查找匹配的本地工具定义
                target_tool = next((t for t in tool_defs if t.name == func_name), None)
                
                if target_tool:
                    try:
                        args = json.loads(args_str)
                        # 执行工具
                        # LLMComponent 作为一个 Component，调用工具时需要传入 context
                        # 如果工具是 Builtin 函数
                        if target_tool.source_type == ToolSourceType.BUILTIN:
                            # 注入 context 如果需要，或直接调用
                            # 这里复用 PluginComponent 的逻辑，或者直接调用 func
                            if getattr(target_tool, 'func', None):
                                res = target_tool.func(**args)
                                if hasattr(res, '__await__'): # Async check
                                    res = await res
                                tool_result_content = json.dumps(res, ensure_ascii=False) if isinstance(res, (dict, list)) else str(res)
                        
                        # 如果是 Plugin (HTTP)，这里暂略，建议复用 PluginComponent 的逻辑
                        
                    except Exception as e:
                        tool_result_content = f"Error executing tool: {str(e)}"
                else:
                    tool_result_content = f"Error: Tool {func_name} not found locally."

                # 将工具结果回填给 LLM
                messages.append(Message.tool(tool_result_content, tool_call_id=call_id))

        # 5. [解析] 结果处理
        final_output = {}
        
        # 模式 A: JSON Object
        if config.response_format == "json_object":
            try:
                cleaned_json = self._clean_json_markdown(final_response_content)
                parsed_data = json.loads(cleaned_json)
                final_output = parsed_data
            except Exception as e:
                logger.error(f"JSON Parse Error: {e}")
                final_output = {"output": final_response_content, "_error": "JSON parse failed"}
        
        # 模式 B: Text
        else:
            # 智能映射：如果前端定义了输出变量名，尝试将结果赋给第一个变量
            output_key = "output"
            if config.output_definitions:
                valid_defs = [d for d in config.output_definitions if d.name not in ["reasoning_content"]]
                if valid_defs:
                    output_key = valid_defs[0].name
            
            final_output[output_key] = final_response_content

        # 注入推理过程 (可选)
        if final_reasoning_content:
            final_output["reasoning_content"] = final_reasoning_content

        return final_output

    # --- Helpers ---

    def _build_json_schema(self, output_defs: List[OutputDefinition]) -> Dict[str, Any]:
        """构建 JSON Schema"""
        if not output_defs: return {}
        
        properties = {}
        required = []
        
        for item in output_defs:
            schema_type = item.type if item.type != "json" else "object"
            prop = {"type": schema_type}
            
            if schema_type == "array":
                prop["items"] = {"type": "string"}
            if schema_type == "object":
                prop["additionalProperties"] = True
            if item.description:
                prop["description"] = item.description
                
            properties[item.name] = prop
            required.append(item.name)
            
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }

    def _clean_json_markdown(self, text: str) -> str:
        """清洗 Markdown 格式的 JSON"""
        text = text.strip()
        pattern = r"^```(?:json)?\s*(\{.*?\})\s*```$"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)
        # 启发式查找大括号
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start : end + 1]
        return text

    def _to_openai_tool(self, tool_def: ToolDefinition) -> Dict:
        """简单的工具定义转换器"""
        # 如果 ToolDefinition 中已经缓存了 openai schema 最好
        # 这里做一个简单的 mock 转换
        return {
            "type": "function",
            "function": {
                "name": tool_def.name,
                "description": tool_def.description or "",
                "parameters": tool_def.args_schema or {"type": "object", "properties": {}}
            }
        }