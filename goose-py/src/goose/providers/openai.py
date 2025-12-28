import os
import json
import logging
from typing import List, Tuple, Optional, Dict, Any, AsyncGenerator, Union

from openai import AsyncOpenAI
from openai import (
    APIConnectionError, 
    RateLimitError, 
    APITimeoutError, 
    AuthenticationError as OpenAIAuthError,
    BadRequestError as OpenAIBadRequestError,
    APIError as OpenAIAPIError
)
from openai.types.chat import ChatCompletionChunk

from ..model import ModelConfig
from ..conversation import (
    Message, Role, TextContent, ToolRequest, ToolResponse, 
    ToolCall, CallToolResult, CallToolRequestParam, RawContent
)
from .base import Provider, ProviderUsage, Usage
from .usage_estimator import ensure_usage_tokens
from .errors import (
    ProviderError, 
    AuthenticationError, 
    RequestFailedError, 
    ContextLengthExceededError,
    UsageError,
    ExecutionError
)
from ..utils.json_repair import repair_and_parse_json

logger = logging.getLogger(__name__)

# --- Constants aligned with Rust implementation ---

OPEN_AI_DEFAULT_MODEL = "gpt-4o"
OPEN_AI_DEFAULT_FAST_MODEL = "gpt-4o-mini"

# Known models and their context limits
OPEN_AI_KNOWN_MODELS = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 128_000,
    "gpt-4.1-mini": 128_000,
    "o1": 200_000,
    "o3": 200_000,
    "gpt-3.5-turbo": 16_385,
    "gpt-4-turbo": 128_000,
    "o4-mini": 128_000,
    "gpt-5.1-codex": 400_000,
    "gpt-5-codex": 400_000,
    "qwen": 32_000, # Fallback generic
}

class OpenAIProvider(Provider):
    def __init__(
        self, 
        model_config: ModelConfig,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        project: Optional[str] = None,
        timeout: float = 600.0,
        extra_headers: Optional[Dict[str, str]] = None
    ):
        self.model_config = model_config
        self.name = "openai"
        
        if not self.model_config.fast_model:
            self.model_config.fast_model = OPEN_AI_DEFAULT_FAST_MODEL

        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url,
            organization=organization,
            project=project,
            timeout=timeout,
            default_headers=extra_headers
        )

    @classmethod
    def from_env(cls, model_config: ModelConfig) -> "OpenAIProvider":
        api_key = os.getenv("OPENAI_API_KEY")
        # Rust logic: default host
        host = os.getenv("OPENAI_HOST", "https://api.openai.com")
        # Rust logic: default base path
        base_path = os.getenv("OPENAI_BASE_PATH", "v1")
        
        # Normalize URL construction
        if "chat/completions" in base_path:
            base_path = base_path.split("chat/completions")[0]
        base_url = f"{host.rstrip('/')}/{base_path.strip('/')}"

        organization = os.getenv("OPENAI_ORGANIZATION")
        project = os.getenv("OPENAI_PROJECT")
        
        try:
            timeout = float(os.getenv("OPENAI_TIMEOUT", "600"))
        except ValueError:
            timeout = 600.0

        custom_headers = {}
        headers_str = os.getenv("OPENAI_CUSTOM_HEADERS")
        if headers_str:
            for item in headers_str.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    custom_headers[k.strip()] = v.strip()

        return cls(
            model_config=model_config,
            api_key=api_key,
            base_url=base_url,
            organization=organization,
            project=project,
            timeout=timeout,
            extra_headers=custom_headers
        )

    def get_name(self) -> str:
        return self.name

    def get_model_config(self) -> ModelConfig:
        return self.model_config

    async def complete(
        self, 
        system: str, 
        messages: List[Message], 
        tools: List[Any] = []
    ) -> Tuple[Message, ProviderUsage]:
        openai_msgs = self._prepare_messages(system, messages)
        openai_tools = self._prepare_tools(tools)

        try:
            # Tool Monitor: Log what we are sending
            if openai_tools:
                logger.debug(f"Sending request with {len(openai_tools)} tools")
            
            response = await self.client.chat.completions.create(
                model=self.model_config.model_name,
                messages=openai_msgs,
                tools=openai_tools,
                stream=False
            )
            
            choice = response.choices[0]
            msg_data = choice.message
            
            content_list = []
            # DeepSeek support (reasoning_content)
            reasoning = getattr(msg_data, "reasoning_content", None)
            content_str = msg_data.content or ""
            
            if reasoning:
                content_str = f"[Thinking]\n{reasoning}\n\n[Answer]\n{content_str}"
            
            if content_str:
                content_list.append(TextContent(text=content_str))
            
            # Extract Tool Calls
            if msg_data.tool_calls:
                for tc in msg_data.tool_calls:
                    try:
                        # [优化] 使用 repair_and_parse_json 替代 json.loads
                        args = repair_and_parse_json(tc.function.arguments)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON args for tool {tc.function.name}: {tc.function.arguments}")
                        # [优化] 如果实在解析不了，将原始内容放入 'raw' 字段，让 Agent 有机会看到错误并重试
                        args = {"error": "json_parse_error", "raw": tc.function.arguments}
                        
                    req = CallToolRequestParam(name=tc.function.name, arguments=args)
                    content_list.append(ToolRequest(
                        id=tc.id,
                        toolCall=ToolCall.success(req)
                    ))

            result_message = Message(role=Role.ASSISTANT, content=content_list)
            
            usage = Usage()
            if response.usage:
                usage = Usage(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens
                )

            provider_usage = ProviderUsage(model=self.model_config.model_name, usage=usage)
            await ensure_usage_tokens(provider_usage, system, messages, result_message, tools)

            return result_message, provider_usage

        except Exception as e:
            self._handle_error(e)

    async def stream(
        self,
        system: str,
        messages: List[Message],
        tools: List[Any] = []
    ) -> AsyncGenerator[Tuple[Optional[Message], Optional[ProviderUsage]], None]:
        
        openai_msgs = self._prepare_messages(system, messages)
        openai_tools = self._prepare_tools(tools)
        
        try:
            stream = await self.client.chat.completions.create(
                model=self.model_config.model_name,
                messages=openai_msgs,
                tools=openai_tools,
                stream=True
            )
        except Exception as e:
            self._handle_error(e)
            return

        final_usage: Optional[ProviderUsage] = None
        accumulated_text: str = ""
        
        # Buffer for parallel tool calling (OpenAI sends chunks by index)
        # Structure: { index: { "id": str, "name": str, "args_parts": [] } }
        tool_call_buffer: Dict[int, Dict[str, Any]] = {}

        try:
            async for chunk in stream:
                # 1. Handle Usage
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = Usage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens
                    )
                    final_usage = ProviderUsage(model=chunk.model, usage=usage)
                    yield None, final_usage

                if not chunk.choices: 
                    continue
                
                delta = chunk.choices[0].delta
                
                # 2. Extract Text & Reasoning
                content_text = ""
                # Standard content
                if hasattr(delta, "content") and delta.content:
                    content_text = delta.content
                elif isinstance(delta, dict) and "content" in delta:
                    content_text = delta["content"]
                
                # DeepSeek/R1 Reasoning
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    # In a real GUI, we might want to separate this. 
                    # For now, we prepend it or stream it as text.
                    content_text = delta.reasoning_content + content_text

                if content_text:
                    accumulated_text += content_text
                    partial = Message(
                        role=Role.ASSISTANT, 
                        content=[TextContent(text=content_text)]
                    )
                    yield partial, None
                
                # 3. Handle Streaming Tool Calls
                tool_calls = getattr(delta, "tool_calls", None)
                if not tool_calls and isinstance(delta, dict):
                    tool_calls = delta.get("tool_calls")

                if tool_calls:
                    for tc in tool_calls:
                        idx = tc.index
                        if idx not in tool_call_buffer:
                            tool_call_buffer[idx] = {"id": "", "name": "", "args_parts": []}
                        
                        # ID usually comes in the first chunk for that index
                        if hasattr(tc, "id") and tc.id: 
                            tool_call_buffer[idx]["id"] = tc.id
                        
                        if hasattr(tc, "function"):
                            fn = tc.function
                            if hasattr(fn, "name") and fn.name: 
                                tool_call_buffer[idx]["name"] = fn.name
                            if hasattr(fn, "arguments") and fn.arguments: 
                                tool_call_buffer[idx]["args_parts"].append(fn.arguments)

                # 4. Finalize Tool Calls on Stop
                finish_reason = getattr(chunk.choices[0], "finish_reason", None)
                if finish_reason in ["tool_calls", "stop", "function_call"] and tool_call_buffer:
                    tool_contents = []
                    
                    # Sort by index to maintain order
                    sorted_indexes = sorted(tool_call_buffer.keys())
                    for idx in sorted_indexes:
                        data = tool_call_buffer[idx]
                        full_args_str = "".join(data["args_parts"])
                        
                        try:
                            # [优化] 使用 repair_and_parse_json
                            if not full_args_str:
                                args_obj = {}
                            else:
                                args_obj = repair_and_parse_json(full_args_str)
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON Parse Error for tool {data['name']}: {e} | Raw: {full_args_str}")
                            # Fallback: expose raw string
                            args_obj = {"error": "json_parse_error", "raw": full_args_str}
                        param = CallToolRequestParam(name=data["name"], arguments=args_obj)
                        
                        # Generate ID if missing (some local models omit ID)
                        call_id = data["id"] or f"call_{idx}_{os.urandom(4).hex()}"
                        
                        tool_contents.append(ToolRequest(
                            id=call_id,
                            toolCall=ToolCall.success(param)
                        ))
                    
                    if tool_contents:
                        yield Message(role=Role.ASSISTANT, content=tool_contents), None

        except Exception as e:
            self._handle_error(e)

        # 5. Usage Fallback
        if final_usage is None:
            full_content_list = []
            if accumulated_text:
                full_content_list.append(TextContent(text=accumulated_text))
            
            # Reconstruct tool calls for token counting
            if tool_call_buffer:
                 for idx in sorted(tool_call_buffer.keys()):
                    data = tool_call_buffer[idx]
                    full_args = "".join(data["args_parts"])
                    param = CallToolRequestParam(name=data["name"], arguments={"raw": full_args})
                    full_content_list.append(ToolRequest(
                        id=data["id"] or "unknown",
                        toolCall=ToolCall.success(param)
                    ))

            full_response_message = Message(role=Role.ASSISTANT, content=full_content_list)
            estimated_usage = ProviderUsage(
                model=self.model_config.model_name, 
                usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0)
            )
            await ensure_usage_tokens(
                estimated_usage, system, messages, full_response_message, tools
            )
            yield None, estimated_usage

    async def get_models(self) -> List[str]:
        try:
            models_page = await self.client.models.list()
            return sorted([model.id for model in models_page.data])
        except Exception as e:
            logger.warning(f"Failed to fetch models: {e}")
            return []

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embedding_model = os.getenv("GOOSE_EMBEDDING_MODEL", "text-embedding-3-small")
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=embedding_model
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            self._handle_error(e)
            return []

    def _prepare_tools(self, tools: List[Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Convert tools to OpenAI format.
        Supports: Dict, Pydantic objects, and MCP-like Tool objects.
        """
        if not tools:
            return None
        
        openai_tools = []
        for tool in tools:
            # 1. Already a Dict (likely pre-formatted)
            if isinstance(tool, dict):
                if "type" in tool and "function" in tool:
                    openai_tools.append(tool)
                else:
                    # Wrap raw function definition
                    openai_tools.append({
                        "type": "function",
                        "function": tool
                    })
            
            # 2. Goose/MCP Tool Object (has to_openai_tool method)
            elif hasattr(tool, "to_openai_tool"):
                openai_tools.append(tool.to_openai_tool())
                
            # 3. Pydantic Model / Generic Object (has model_dump)
            elif hasattr(tool, "model_dump"):
                tool_dump = tool.model_dump(exclude_none=True)
                if "type" in tool_dump and "function" in tool_dump:
                    openai_tools.append(tool_dump)
                else:
                    openai_tools.append({
                        "type": "function",
                        "function": tool_dump
                    })
            else:
                logger.warning(f"Skipping unknown tool format: {type(tool)}")
        
        return openai_tools

    def _prepare_messages(self, system: str, history: List[Message]) -> List[Dict[str, Any]]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        
        for msg in history:
            if not msg.metadata.agent_visible:
                continue

            # --- Assistant Role (Text + Tool Requests) ---
            if msg.role == Role.ASSISTANT:
                openai_msg = {"role": "assistant"}
                
                content_text = ""
                tool_calls = []
                
                for c in msg.content:
                    if isinstance(c, TextContent):
                        content_text += c.text
                    elif isinstance(c, ToolRequest):
                        if c.tool_call.status == "success" and c.tool_call.value:
                            tc = c.tool_call.value
                            tool_calls.append({
                                "id": c.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments or {})
                                }
                            })
                
                if content_text: openai_msg["content"] = content_text
                if tool_calls: openai_msg["tool_calls"] = tool_calls
                messages.append(openai_msg)

            # --- User or Tool Role ---
            # Goose 可能会把 ToolResponse 放在 User Role 下，也可能放在 Tool Role 下
            # 我们需要把它们拆开
            elif msg.role == Role.USER or msg.role == Role.TOOL:
                text_parts = []
                tool_responses = []
                
                for c in msg.content:
                    if isinstance(c, TextContent):
                        text_parts.append(c.text)
                    elif isinstance(c, ToolResponse):
                        tool_responses.append(c)
                
                # 发送纯文本部分 (作为 User 消息)
                if text_parts:
                    messages.append({
                        "role": "user", 
                        "content": "\n".join(text_parts)
                    })
                
                # 发送工具结果部分 (作为 Tool 消息)
                for tr in tool_responses:
                    content_str = ""
                    # [修复] 适配 CallToolResult 的结构
                    if tr.tool_result.is_error:
                        # 错误情况提取文本
                        texts = [rc.text for rc in tr.tool_result.content if rc.text]
                        content_str = f"Error: {', '.join(texts)}"
                    else:
                        # 成功情况提取文本
                        texts = [rc.text for rc in tr.tool_result.content if rc.text]
                        content_str = "".join(texts)
                        # 如果有二进制数据，OpenAI 暂不支持，忽略或标记
                    
                    if not content_str:
                        content_str = "Success" 

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr.id,
                        "content": content_str
                    })

        return messages

    def _handle_error(self, e: Exception):
        """Map OpenAI exceptions to Goose ProviderError hierarchy"""
        error_msg = str(e)
        logger.error(f"OpenAI API Error: {error_msg}")
        
        if isinstance(e, OpenAIAuthError):
            raise AuthenticationError(f"OpenAI Authentication Failed: {error_msg}")
        
        elif isinstance(e, OpenAIBadRequestError):
            if "context_length_exceeded" in error_msg:
                raise ContextLengthExceededError(error_msg)
            raise UsageError(f"Bad Request: {error_msg}")
            
        elif isinstance(e, (APIConnectionError, APITimeoutError)):
            raise RequestFailedError(f"Connection Failed: {error_msg}")
            
        elif isinstance(e, RateLimitError):
            raise RequestFailedError(f"Rate Limit Exceeded: {error_msg}")
            
        elif isinstance(e, OpenAIAPIError):
            raise ExecutionError(f"OpenAI Server Error: {error_msg}")
            
        else:
            raise ExecutionError(f"Unexpected Error: {error_msg}")