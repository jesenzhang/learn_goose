"""
OpenAI Provider

OpenAI provider implementation for LLM and Embedding.
Reference: assistant OpenAI provider implementation.
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple

import httpx

logger = logging.getLogger("goose.providers.openai")

try:
    from openai import AsyncOpenAI
    from openai import (
        APIConnectionError,
        RateLimitError,
        APITimeoutError,
        AuthenticationError as OpenAIAuthError,
        BadRequestError as OpenAIBadRequestError,
        APIError as OpenAIAPIError
    )
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

from .base import (
    BaseLLM, BaseEmbedding, Provider, ProviderUsage, Usage,
    ModelConfig, InferenceConfig, Document
)
from .factory import ProviderFactory
from ..conversation.message import Message, Role, TextContent, ToolRequestContent, ToolResponseContent, ImageContent
from ..tools.base import ToolRequest
from .errors import (
    ProviderError, AuthenticationError, RequestFailedError,
    ContextLengthExceededError, UsageError, ExecutionError
)


@ProviderFactory.register_llm("openai")
@ProviderFactory.register_embedding("openai")
class OpenAIProvider(BaseLLM, BaseEmbedding):
    """
    OpenAI Provider implementing BaseLLAI and BaseEmbedding interfaces.

    Supports:
    - GPT-4, GPT-4 Turbo, GPT-3.5 Turbo
    - Embeddings (text-embedding-3-small, text-embedding-3-large)
    - Streaming responses
    - Tool calling
    """

    def __init__(self, config: ModelConfig | Dict[str, Any]):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package is required. Install with: pip install openai")

        self.name = "openai"

        if isinstance(config, dict):
            config = ModelConfig(**config)
        elif not isinstance(config, ModelConfig):
            raise TypeError("config must be a dict or ModelConfig")

        self.model_config = config

        api_key = config.api_key or os.getenv(config.api_key_env)
        if not api_key:
            raise ValueError(f"API Key missing. Check config or {config.api_key_env}")

        base_url = config.base_url
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"

        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout or 60.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=config.organization,
            project=config.project,
            http_client=self.http_client,
            default_headers=config.extra_headers
        )

        logger.info(f"OpenAI Provider initialized: model={config.model_name}, base_url={base_url}")

        self.inference_config = config.get_inference_config()
        self._sem = asyncio.Semaphore(50)

    async def aclose(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    def get_model_config(self) -> ModelConfig:
        """Get model configuration."""
        return self.model_config

    async def agenerate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Tuple[Message, Optional[ProviderUsage]]:
        """Generate complete response."""
        openai_msgs = self._prepare_messages(messages)
        openai_tools = self._prepare_tools(tools)

        merged_config = self.inference_config.merge(**kwargs)

        payload = {
            "model": self.model_config.model_name,
            "messages": openai_msgs,
            "stream": False
        }
        payload.update(merged_config.to_api_params())

        if stop:
            payload["stop"] = stop

        if openai_tools:
            payload["tools"] = openai_tools

        async with self._sem:
            try:
                response = await self.client.chat.completions.create(**payload)
                choice = response.choices[0]
                msg_data = choice.message

                content_list = []
                content_str = msg_data.content or ""

                if content_str:
                    content_list.append(TextContent(text=content_str))

                if msg_data.tool_calls:
                    for tc in msg_data.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except json.JSONDecodeError:
                            args = {"raw": tc.function.arguments}
                        content_list.append(ToolRequestContent(
                            id=tc.id,
                            tool_call={
                                "status": "success",
                                "value": {
                                    "name": tc.function.name,
                                    "arguments": args
                                }
                            }
                        ))

                result_message = Message(role=Role.ASSISTANT, content=content_list)
                usage_info = None
                if response.usage:
                    usage_info = ProviderUsage(
                        model=self.model_config.model_name,
                        usage=Usage(
                            input_tokens=response.usage.prompt_tokens,
                            output_tokens=response.usage.completion_tokens,
                            total_tokens=response.usage.total_tokens
                        )
                    )

                return result_message, usage_info

            except Exception as e:
                self._handle_error(e)
                raise

    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncGenerator[Tuple[Message, Optional[ProviderUsage]], None]:
        """Generate streaming response."""
        openai_msgs = self._prepare_messages(messages)
        openai_tools = self._prepare_tools(tools)

        merged_config = self.inference_config.merge(**kwargs)

        payload = {
            "model": self.model_config.model_name,
            "messages": openai_msgs,
            "stream": True
        }
        payload.update(merged_config.to_api_params())

        if stop:
            payload["stop"] = stop

        if openai_tools:
            payload["tools"] = openai_tools

        async with self._sem:
            try:
                stream = await self.client.chat.completions.create(**payload)

                tool_buffer: Dict[int, Dict[str, Any]] = {}

                async for chunk in stream:
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage_info = ProviderUsage(
                            model=self.model_config.model_name,
                            usage=Usage(
                                input_tokens=chunk.usage.prompt_tokens,
                                output_tokens=chunk.usage.completion_tokens,
                                total_tokens=chunk.usage.total_tokens
                            )
                        )
                        yield Message(role=Role.ASSISTANT), usage_info

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    if delta.content:
                        yield Message(
                            role=Role.ASSISTANT,
                            content=[TextContent(text=delta.content)]
                        ), None

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_buffer:
                                tool_buffer[idx] = {"id": "", "name": "", "args": ""}
                            if tc.id:
                                tool_buffer[idx]["id"] = tc.id
                            if tc.function.name:
                                tool_buffer[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_buffer[idx]["args"] += tc.function.arguments

                    if chunk.choices[0].finish_reason in ["tool_calls", "stop"] and tool_buffer:
                        tool_reqs = []
                        for idx in sorted(tool_buffer.keys()):
                            data = tool_buffer[idx]
                            args_str = data["args"]
                            try:
                                args = json.loads(args_str) if args_str else {}
                            except json.JSONDecodeError:
                                args = {"raw": args_str}

                            cid = data["id"] or f"call_{idx}_{os.urandom(4).hex()}"

                            tool_reqs.append(ToolRequest(
                                id=cid,
                                name=data["name"],
                                arguments=args
                            ))

                        if tool_reqs:
                            yield Message(role=Role.ASSISTANT, content=tool_reqs), None

            except Exception as e:
                self._handle_error(e)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for documents."""
        if not texts:
            return []

        try:
            embedding_model = getattr(self.model_config, 'embedding_model_name', None) or self.model_config.model.model_name
            response = await self.client.embeddings.create(
                input=texts,
                model=embedding_model,
                encoding_format="float"
            )
            return [d.embedding for d in sorted(response.data, key=lambda x: x.index)]
        except Exception as e:
            self._handle_error(e)
            return []

    async def aembed_query(self, text: str) -> List[float]:
        """Generate embedding for query."""
        res = await self.aembed_documents([text])
        return res[0] if res else []

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Prepare messages for OpenAI API."""
        openai_msgs = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                openai_msgs.append({"role": "system", "content": msg.text})

            elif msg.role == Role.USER:
                content_list = []
                text_parts = []
                image_parts = []

                for c in msg.content:
                    if isinstance(c, TextContent):
                        text_parts.append(c.text)
                    elif isinstance(c, ImageContent):
                        # Convert from ImageContent to OpenAI format
                        image_parts.append(c.to_openai_dict())

                if text_parts:
                    content_list.append({"type": "text", "text": "\n".join(text_parts)})
                if image_parts:
                    content_list.extend(image_parts)

                if len(content_list) == 1 and content_list[0].get("type") == "text":
                    openai_msgs.append({"role": "user", "content": msg.text})
                elif content_list:
                    openai_msgs.append({"role": "user", "content": content_list})
                else:
                    openai_msgs.append({"role": "user", "content": msg.text})

            elif msg.role == Role.ASSISTANT:
                o_msg = {"role": "assistant"}
                content_parts = []
                tool_reqs = []

                for c in msg.content:
                    if isinstance(c, TextContent):
                        content_parts.append(c.text)
                    elif isinstance(c, ToolRequestContent):
                        value = c.tool_call_value
                        if value:
                            tool_reqs.append(c)

                if content_parts:
                    o_msg["content"] = "\n\n".join(content_parts)

                if tool_reqs:
                    o_msg["tool_calls"] = []
                    for req in tool_reqs:
                        value = req.tool_call_value
                        if value:
                            o_msg["tool_calls"].append({
                                "id": req.id,
                                "type": "function",
                                "function": {
                                    "name": value.name,
                                    "arguments": json.dumps(value.arguments or {})
                                }
                            })

                openai_msgs.append(o_msg)

            elif msg.role == Role.TOOL:
                for c in amsg.content:
                    if isinstance(c, ToolResponseContent):
                        content_str = str(c.result) if c.result else "Success"
                        if c.is_error:
                            content_str = f"Error: {content_str}"

                        openai_msgs.append({
                            "role": "tool",
                            "tool_call_id": c.id,
                            "content": content_str
                        })

        return openai_msgs

    def _prepare_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict]]:
        """Prepare tools for OpenAI API."""
        if not tools:
            return None
        return [self._convert_tool(t) for t in tools]

    def _convert_tool(self, tool: Any) -> Dict:
        """Convert tool to OpenAI format."""
        if isinstance(tool, dict):
            if "type" not in tool:
                return {"type": "function", "function": tool}
            return tool
        if hasattr(tool, "to_dict"):
            return tool.to_dict()
        return {"type": "function", "function": tool}

    def _handle_error(self, e: Exception):
        """Handle and map exceptions."""
        msg = str(e)
        if isinstance(e, OpenAIAuthError):
            raise AuthenticationError(f"Auth Failed: {msg}")
        elif isinstance(e, OpenAIBadRequestError):
            if "context_length" in msg:
                raise ContextLengthExceededError(msg)
            raise UsageError(f"Bad Request: {msg}")
        elif isinstance(e, (APIConnectionError, APITimeoutError)):
            raise RequestFailedError(f"Connection Failed: {msg}")
        elif isinstance(e, RateLimitError):
            raise RequestFailedError(f"Rate Rate: {msg}")
        elif isinstance(e, OpenAIAPIError):
            raise ExecutionError(f"OpenAI Error: {msg}")
        else:
            raise ExecutionError(f"Unexpected: {msg}")
