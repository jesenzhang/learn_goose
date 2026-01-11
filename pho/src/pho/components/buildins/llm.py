import json
import re
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from pho.components.base import Component
from pho.toolkit import tool_registry, ToolSourceType, ToolDefinition
from pho.workflow.context import WorkflowContext
from pho.utils.template import TemplateRenderer
from pho.conversation import Message, Role, TextContent
from pho.components.registry import register_component
from pho.types import NodeTypes
from pho.events.types import SystemEvents

from pho.providers.base import BaseLLM  # 引入系统事件

logger = logging.getLogger("pho.component.llm")

# ==========================================
# Schema Definition
# ==========================================

class OutputDefinition(BaseModel):
    name: str
    type: str = "string"
    description: Optional[str] = None

class LLMConfig(BaseModel):
    # --- 模型配置 ---
    model: str = Field(..., description="模型资源ID (e.g. sys.model.gpt4o)")
    id: Optional[str] = Field(None, description="运行时注入的节点 ID")
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

@register_component(
    name=NodeTypes.LLM,
    group="AI",
    label="大语言模型",
    description="执行对话、工具调用及结构化输出",
    icon="cpu",
    author="System",
    version="1.0.0",
    config_model=LLMConfig
)
class LLMComponent(Component):
    async def execute(
        self, 
        inputs: Dict[str, Any], 
        config: LLMConfig, 
        context: WorkflowContext
    ) -> Dict[str, Any]:
        
        # 1. [准备] 工具定义
        tool_defs = []
        openai_tools = []
        
        if config.tools:
            for tool_id in config.tools:
                t_def = tool_registry.get_meta(tool_id)
                if t_def:
                    tool_defs.append(t_def)
                    # 转换工具定义格式
                    openai_tools.append(self._to_openai_tool(t_def))
                else:
                    logger.warning(f"Tool not found: {tool_id}")

        # 2. [准备] 模型 Provider
        # 从资源管理器获取已初始化的 Provider 实例 (单例)
        try:
            provider:BaseLLM = await context.resources.get_instance(config.model)
        except Exception as e:
            raise ValueError(f"Failed to load model resource '{config.model}': {e}")

        # 3. [渲染] Prompt
        system_instruction = config.system_prompt
        
        # JSON Schema 注入
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

        # 渲染变量
        system_content = TemplateRenderer.render(system_instruction, inputs)
        user_content = TemplateRenderer.render(config.prompt, inputs)
        
        # 初始化消息历史
        # 注意：Prompt 不包含在 messages 列表中，而是作为 system/user 参数传给 Provider
        # 但为了 ReAct 循环，我们需要维护一个本地的 messages 列表
        current_messages: List[Message] = []
        if system_content:
            current_messages.append(Message.system(system_content))
        
        current_messages.append(Message.user(user_content))
        

        # 4. [执行] ReAct Loop
        current_iter = 0
        final_response_content = ""
        final_reasoning_content = ""
        
        while current_iter < config.max_iterations:
            current_iter += 1
            
            # --- Stream Loop ---
            accumulated_text = ""
            current_tool_msg: Optional[Message] = None
            
            # 使用 provider.stream 获取打字机效果
            # 传递 tools 参数：如果是空列表，传 None，或者取决于 Provider 实现
            # 之前的 OpenAIProvider 修复版支持传空列表，这里传 openai_tools or None 最稳妥
            async for partial_msg, usage in provider.astream(
                messages=current_messages,
                tools=openai_tools or None,
                temperature=config.temperature
            ):
                if partial_msg:
                    # Case A: 文本流
                    if partial_msg.content and isinstance(partial_msg.content[0], TextContent):
                        text_chunk = partial_msg.content[0].text
                        accumulated_text += text_chunk
                        # [Core] 推送流式 Token 到 EventBus
                        await context.streamer.emit(
                            SystemEvents.STREAM_TOKEN, 
                            text_chunk, 
                            producer_id=config.id
                        )
                    
                    # Case B: 工具调用消息 (通常在流结束时由 Provider 组装好返回)
                    # 根据你的 OpenAIProvider 实现，含有 tool_calls 的 message 会作为 partial_msg 返回
                    if partial_msg.tool_calls:
                        current_tool_msg = partial_msg

                # Usage 暂时忽略，或者累加

            # Stream 结束，处理结果
            
            # 如果有工具调用
            if current_tool_msg and current_tool_msg.tool_calls:
                # 将 Assistant 的工具调用消息加入历史
                current_messages.append(current_tool_msg)
                
                logger.info(f"🔧 Tool Calls detected: {len(current_tool_msg.tool_calls)}")
                
                # 执行所有工具
                for tool_call_req in current_tool_msg.tool_calls:
                    # 解包 Request
                    # ToolRequest(id=..., toolCall=Result(value=CallToolRequestParam(...)))
                    if tool_call_req.tool_call.is_error:
                        continue
                        
                    param = tool_call_req.tool_call.value
                    call_id = tool_call_req.id
                    func_name = param.name
                    args = param.arguments

                    tool_result_content = ""
                    
                    # 查找本地工具定义
                    target_tool = next((t for t in tool_defs if t.name == func_name), None)
                    
                    if target_tool:
                        try:
                            # 执行工具 (支持 Sync 和 Async)
                            if target_tool.source_type == ToolSourceType.BUILTIN:
                                if getattr(target_tool, 'func', None):
                                    # [Core] 注入 context (如果工具函数需要)
                                    # 这里做一个简单的参数检测，或者约定工具函数签名
                                    # 简单起见，直接传 args
                                    res = target_tool.func(**args)
                                    if hasattr(res, '__await__'): 
                                        res = await res
                                    tool_result_content = json.dumps(res, ensure_ascii=False) if isinstance(res, (dict, list)) else str(res)
                            else:
                                tool_result_content = "Plugin tools not implemented yet"
                        except Exception as e:
                            tool_result_content = f"Error executing tool: {str(e)}"
                    else:
                        tool_result_content = f"Error: Tool {func_name} not found."

                    # 将工具结果回填给 LLM (作为 Tool Message)
                    current_messages.append(Message.tool(tool_result_content, tool_call_id=call_id))
                
                # 继续下一轮循环 (Chat with Tool Results)
                continue

            else:
                # 没有工具调用，这是最终回复
                # 将纯文本回复加入历史 (保持完整性)
                assistant_msg = Message.assistant(accumulated_text)
                current_messages.append(assistant_msg)
                
                final_response_content = accumulated_text
                break
        
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
        text = text.strip()
        pattern = r"^```(?:json)?\s*(\{.*?\})\s*```$"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start : end + 1]
        return text

    def _to_openai_tool(self, tool_def: ToolDefinition) -> Dict:
        return {
            "type": "function",
            "function": {
                "name": tool_def.name,
                "description": tool_def.description or "",
                "parameters": tool_def.args_schema or {"type": "object", "properties": {}}
            }
        }