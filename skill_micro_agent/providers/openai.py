"""
OpenAI Implementation for MicroAgent Services.
Integrates LLM and Embedding capabilities.
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple, Union

import httpx
from openai import AsyncOpenAI
from openai import (
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
    AuthenticationError as OpenAIAuthError,
    BadRequestError as OpenAIBadRequestError,
    APIError as OpenAIAPIError
)
from pydantic import model_validator
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type

# Core Interfaces

from .model_config import ModelConfig
from .base import BaseLLM, BaseEmbedding
from .factory import ProviderFactory
from ..conversation import (
    Message as Message,
    Role,
    TextContent,
    ToolRequest,
    ToolResponse,
    ToolCall,
    CallToolResult,
    CallToolRequestParam,
    RawContent
)

# Utils & Errors
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

@ProviderFactory.register_llm("openai")
@ProviderFactory.register_embedding("openai")
class OpenAIProvider(BaseLLM, BaseEmbedding):
    """
    Unified OpenAI Provider implementing BaseLLM and BaseEmbedding interfaces.
    """

    def __init__(self, config: ModelConfig|Dict[str, Any]):
        """
        初始化只需传入一个 config 对象。
        所有的参数提取、默认值回退逻辑都在这里处理。
        """
        self.name = "openai"

        if isinstance(config, dict):
            config = ModelConfig.model_validate(config)
        elif not isinstance(config, ModelConfig):
            raise TypeError("config must be a dict or ModelConfig")

        self.model_config = config

        # 1. 决定 API Key (Config优先 > Env兜底)
        api_key = config.api_key or os.getenv(config.api_key_env)
        if not api_key:
            raise ValueError(f"API Key missing. Check config or {config.api_key_env}")

        # 2. 决定 Base URL (处理结尾斜杠等细节)
        base_url = config.base_url
        if base_url:
            # Normalize base_url: remove trailing slashes
            base_url = base_url.rstrip("/")
            # Ensure it ends with /v1 for OpenAI compatibility
            if not base_url.endswith("/v1"):
                # If it doesn't end with /v1, append it
                base_url = f"{base_url}/v1"

        # 3. 初始化 HTTP Client
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout or 60.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )

        # 4. 初始化 SDK Client
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=config.organization,
            project=config.project,
            http_client=self.http_client,
            default_headers=config.extra_headers
        )

        # Log the connection details for debugging
        logger.info(f"OpenAI Provider initialized: model={config.model_name}, base_url={base_url}")

        # 提取推理配置（运行时参数）
        self.inference_config = config.get_inference_config()

        self._sem = asyncio.Semaphore(50) # 并发控制

    async def close(self):
        await self.http_client.aclose()

    def get_name(self) -> str:
        return self.name

    def get_model_config(self) -> ModelConfig:
        return self.model_config
    # =========================================================================
    # BaseLLM Implementation
    # =========================================================================

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError))
    )
    async def agenerate(
        self,
        messages: List[Message],  # Using Goose Message format
        tools: Optional[List[Any]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[Message, Any]: # Returning (Message, Usage)

        openai_msgs = self._prepare_messages(messages)
        openai_tools = self._prepare_tools(tools)

        # 合并配置参数和运行时参数
        # 优先级：kwargs > base_inference_config > defaults
        merged_config = self.inference_config.merge(**kwargs)

        # 构建请求参数
        payload = {
            "model": self.model_config.model_name,
            "messages": openai_msgs,
            "stream": False
        }

        # 从合并后的配置获取参数
        payload.update(merged_config.to_api_params())

        # stop 参数有单独的函数参数，优先级最高
        if stop:
            payload["stop"] = stop

        if openai_tools:
            payload["tools"] = openai_tools

        async with self._sem:
            try:
                response = await self.client.chat.completions.create(**payload)

                choice = response.choices[0]
                msg_data = choice.message

                # --- Convert OpenAI Response to Goose Message ---
                content_list = []

                # 1. Handle Text Content
                content_str = msg_data.content or ""
                # DeepSeek/R1 reasoning support
                reasoning = getattr(msg_data, "reasoning_content", None)
                if reasoning:
                    content_str = f"[Thinking]\n{reasoning}\n\n[Answer]\n{content_str}"

                if content_str:
                    content_list.append(TextContent(text=content_str))

                # 2. Handle Tool Calls
                if msg_data.tool_calls:
                    for tc in msg_data.tool_calls:
                        try:
                            args = repair_and_parse_json(tc.function.arguments)
                        except Exception:
                            logger.warning(f"JSON Parse Failed: {tc.function.arguments}")
                            args = {"error": "parse_error", "raw": tc.function.arguments}

                        req = CallToolRequestParam(name=tc.function.name, arguments=args)
                        content_list.append(ToolRequest(
                            id=tc.id,
                            toolCall=ToolCall.success(req)
                        ))

                result_message = Message(role=Role.ASSISTANT, content=content_list)

                # 3. Handle Usage
                usage_info = None
                if response.usage:
                    # Creating a simple dict or your Usage object
                    usage_info = {
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }

                return result_message, usage_info

            except Exception as e:
                self._handle_error(e)
                raise # Should be unreachable due to handle_error re-raising

    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> AsyncGenerator[Tuple[Message, Any], None]:

        openai_msgs = self._prepare_messages(messages)
        openai_tools = self._prepare_tools(tools)

        # 合并配置参数和运行时参数（与 agenerate 一致）
        merged_config = self.inference_config.merge(**kwargs)

        # 构建请求参数
        payload = {
            "model": self.model_config.model_name,
            "messages": openai_msgs,
            "stream": True
        }

        # 从合并后的配置获取参数
        payload.update(merged_config.to_api_params())

        # stop 参数有单独的函数参数，优先级最高
        if stop:
            payload["stop"] = stop

        if openai_tools:
            payload["tools"] = openai_tools

        # Retry logic for connection establishment only
        @retry(
            wait=wait_random_exponential(min=1, max=60),
            stop=stop_after_attempt(5),
            retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
            reraise=True
        )
        async def _connect():
            return await self.client.chat.completions.create(**payload)

        try:
            async with self._sem:
                stream = await _connect()

                tool_buffer = {} # {index: {id, name, args_parts}}

                async for chunk in stream:
                    # 1. Emit Usage (often in last chunk)
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage_info = {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                        # Yield usage marker
                        yield Message(role=Role.ASSISTANT), usage_info

                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta

                    # 2. Stream Text
                    content = delta.content or ""
                    reasoning = getattr(delta, "reasoning_content", "")

                    full_text = reasoning + content
                    if full_text:
                        yield Message(role=Role.ASSISTANT, content=[TextContent(text=full_text)]), None

                    # 3. Stream Tool Calls
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_buffer:
                                tool_buffer[idx] = {"id": "", "name": "", "args": []}

                            if tc.id: tool_buffer[idx]["id"] = tc.id
                            if tc.function.name: tool_buffer[idx]["name"] = tc.function.name
                            if tc.function.arguments: tool_buffer[idx]["args"].append(tc.function.arguments)

                    # 4. Finalize Tools on Stop
                    if chunk.choices[0].finish_reason in ["tool_calls", "stop"] and tool_buffer:
                        tool_reqs = []
                        for idx in sorted(tool_buffer.keys()):
                            data = tool_buffer[idx]
                            args_str = "".join(data["args"])
                            try:
                                args = repair_and_parse_json(args_str) if args_str else {}
                            except:
                                args = {"raw": args_str}

                            # Fallback ID generation
                            cid = data["id"] or f"call_{idx}_{os.urandom(4).hex()}"

                            tool_reqs.append(ToolRequest(
                                id=cid,
                                toolCall=ToolCall.success(CallToolRequestParam(name=data["name"], arguments=args))
                            ))

                        if tool_reqs:
                            yield Message(role=Role.ASSISTANT, content=tool_reqs), None

        except Exception as e:
            self._handle_error(e)

    # =========================================================================
    # BaseEmbedding Implementation
    # =========================================================================

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts: return []
        try:
            # TODO: Implement batching logic if texts > 2048
            res = await self.client.embeddings.create(
                input=texts,
                model=self.model_config.embedding_model_name,
                encoding_format="float"
            )
            return [d.embedding for d in sorted(res.data, key=lambda x: x.index)]
        except Exception as e:
            self._handle_error(e)
            return []

    async def aembed_query(self, text: str) -> List[float]:
        res = await self.aembed_documents([text])
        return res[0] if res else []

    # =========================================================================
    # Internal Helpers (Adapted from Goose)
    # =========================================================================

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        openai_msgs = []
        for msg in messages:
            # Skip invisible messages (system logic)
            if not msg.metadata.agent_visible: continue

            if msg.role == Role.SYSTEM:
                openai_msgs.append({"role": "system", "content": msg.text})

            elif msg.role == Role.USER:
                openai_msgs.append({"role": "user", "content": msg.text})

            elif msg.role == Role.ASSISTANT:
                o_msg = {"role": "assistant"}
                text_parts = [c.text for c in msg.content if isinstance(c, TextContent)]
                if text_parts: o_msg["content"] = "\n".join(text_parts)

                tool_reqs = [c for c in msg.content if isinstance(c, ToolRequest)]
                if tool_reqs:
                    o_msg["tool_calls"] = [{
                        "id": req.id,
                        "type": "function",
                        "function": {
                            "name": req.tool_call.value.name,
                            "arguments": json.dumps(req.tool_call.value.arguments or {})
                        }
                    } for req in tool_reqs if req.tool_call.value]

                openai_msgs.append(o_msg)

            elif msg.role == Role.TOOL:
                # Goose stores ToolResponses in TOOL role messages
                # OpenAI expects each tool response as a separate message with role='tool'
                for c in msg.content:
                    if isinstance(c, ToolResponse):
                        content_str = ""
                        if c.tool_result.is_error:
                            content_str = f"Error: {c.tool_result.content[0].text}" if c.tool_result.content else "Error"
                        else:
                            # Concat all text content parts
                            parts = [rc.text for rc in c.tool_result.content if rc.text]
                            content_str = "\n".join(parts) if parts else "Success"

                        openai_msgs.append({
                            "role": "tool",
                            "tool_call_id": c.id,
                            "content": content_str
                        })

        return openai_msgs

    def _prepare_tools(self, tools: Optional[List[Any]]) -> Optional[List[Dict]]:
        if not tools: return None
        return [self._convert_tool(t) for t in tools]

    def _convert_tool(self, tool: Any) -> Dict:
        """Helper to unify tool format to OpenAI Schema"""
        if isinstance(tool, dict): return tool
        if hasattr(tool, "to_openai_tool"): return tool.to_openai_tool()
        if hasattr(tool, "model_dump"):
            d = tool.model_dump(exclude_none=True)
            if "type" not in d: # Wrap if it's just parameters
                return {"type": "function", "function": d}
            return d
        return {"type": "function", "function": tool} # Fallback

    def _handle_error(self, e: Exception):
        """Map exceptions to unified ProviderErrors"""
        msg = str(e)
        if isinstance(e, OpenAIAuthError):
            raise AuthenticationError(f"Auth Failed: {msg}")
        elif isinstance(e, OpenAIBadRequestError):
            if "context_length" in msg: raise ContextLengthExceededError(msg)
            raise UsageError(f"Bad Request: {msg}")
        elif isinstance(e, (APIConnectionError, APITimeoutError)):
            raise RequestFailedError(f"Connection Failed: {msg}")
        elif isinstance(e, RateLimitError):
            raise RequestFailedError(f"Rate Limit: {msg}")
        elif isinstance(e, OpenAIAPIError):
            raise ExecutionError(f"OpenAI Error: {msg}")
        else:
            raise ExecutionError(f"Unexpected: {msg}")



