"""
Anthropic Provider

Anthropic Claude provider implementation.
Supports Claude 3.5 Sonnet, Claude 3 Opus, etc.
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple

import httpx

logger = logging.getLogger("goose.providers.anthropic")

try:
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic import (
        APIError as AnthropicAPIError,
        AuthenticationError as AnthropicAuthError,
        RateLimitError as AnthropicRateLimitError,
        BadRequestError as AnthropicBadRequestError,
        APIConnectionError as AnthropicConnectionError,
    )
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None
    AsyncAnthropic = None

from .base import (
    BaseLLM, BaseEmbedding, Provider, ProviderUsage, Usage,
    ModelConfig, InferenceConfig
)
from .factory import ProviderFactory
from ..conversation.message import Message, Role, TextContent, ToolRequestContent, ToolResponseContent, ImageContent
from .errors import (
    ProviderError, AuthenticationError, RequestFailedError,
    ContextLengthExceededError, UsageError, ExecutionError
)


ANTHROPIC_DEFAULT_MODELS = {
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-5-sonnet-20240620": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "claude-sonnet-4-20250520": 200000,
}


@ProviderFactory.register_llm("anthropic")
class AnthropicProvider(BaseLLM):
    """
    Anthropic Claude provider implementation.
    """

    def __init__(self, config: ModelConfig | Dict[str, Any]):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package is required. Install with: pip install anthropic")

        self.name = "anthropic"

        if isinstance(config, dict):
            config = ModelConfig(**config)
        elif not isinstance(config, ModelConfig):
            raise TypeError("config must be a dict or ModelConfig")

        self.model_config = config

        api_key = config.api_key or os.getenv(config.api_key_env, "")
        if not api_key:
            raise ValueError(f"API Key missing. Check config or {config.api_key_env}")

        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout or 60.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )

        self.client = AsyncAnthropic(
            api_key=api_key,
            http_client=self.http_client,
            default_headers=config.extra_headers
        )

        logger.info(f"Anthropic Provider initialized: model={config.model_name}")

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
        anthropic_msgs = self._prepare_messages(messages)
        anthropic_tools = self._prepare_tools(tools)
        system_prompt = self._extract_system_prompt(messages)

        merged_config = self.inference_config.merge(**kwargs)

        payload = {
            "model": self.model_config.model_name,
            "messages": anthropic_msgs,
            "stream": False,
            "max_tokens": merged_config.max_tokens or self.model_config.context_limit
        }

        if (system_prompt):
            payload["system"] = system_prompt

        if stop:
            payload["stop_sequences"] = stop

        if anthropic_tools:
            payload["tools"] = anthropic_tools

        async with self._sem:
            try:
                response = await self.client.messages.create(**payload)
                content_list = []

                for block in response.content:
                    if block.type == "text":
                        content_list.append(TextContent(text=block.text))
                    elif block.type == "tool_use":
                        value = block.input or {}
                        content_list.append(ToolRequestContent.create(
                            tool_id=block.id,
                            name=block.name,
                            arguments=value
                        ))

                result_message = Message(role=Role.ASSISTANT, content=content_list)

                usage_info = None
                if response.usage:
                    usage_info = ProviderUsage(
                        model=self.model_config.model_name,
                        usage=Usage(
                            input_tokens=response.usage.input_tokens,
                            output_tokens=response.usage.output_tokens,
                            total_tokens=response.usage.input_tokens + response.usage.output_tokens
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
        anthropic_msgs = self._prepare_messages(messages)
        anthropic_tools = self._prepare_tools(tools)
        system_prompt = self._extract_system_prompt(messages)

        merged_config = self.inference_config.merge(**kwargs)

        payload = {
            "model": self.model_config.model_name,
            "messages": anthropic_msgs,
            "stream": True,
            "max_tokens": merged_config.max_tokens or self.model_config.context_limit
        }

        if system_prompt:
            payload["system"] = system_prompt

        if stop:
            payload["stop_sequences"] = stop

        if anthropic_tools:
            payload["tools"] = anthropic_tools

        async with self._sem:
            try:
                stream = await self.client.messages.create(**payload)

                async for event in stream:
                    if hasattr(event, "usage") and event.usage:
                        usage_info = ProviderUsage(
                            model=self.model_config.model_name,
                            usage=Usage(
                                input_tokens=event.usage.input_tokens,
                                output_tokens=event.usage.output_tokens,
                                total_tokens=event.usage.input_tokens + event.usage.output_tokens
                        )
                        )
                        yield Message(role=Role.ASSISTANT), usage_info

                    if event.type == "content_block_delta":
                        if hasattr(event, "delta") and hasattr(event.delta, "text"):
                            yield Message(
                                role=Role.ASSISTANT,
                                content=[TextContent(text=event.delta.text)]
                            ), None

                    elif event.type == "content_block_stop":
                        if hasattr(event, "content_block"):
                            content_list = []
                            for block in event.content_block:
                                if block.type == "tool_use":
                                    value = block.input or {}
                                    content_list.append(ToolRequestContent.create(
                                        tool_id=block.id,
                                        name=block.name,
                                        arguments=value
                                    ))
                            if content_list:
                                yield Message(role=Role.ASSISTANT, content=content_list), None

            except Exception as e:
                self._handle_error(e)

    def _extract_system_prompt(self, messages: List[Message]) -> Optional[str]:
        """Extract system prompt from messages."""
        for msg in messages:
            if msg.role == Role.SYSTEM:
                return msg.text
        return None

    def _prepare_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Prepare messages for Anthropic API."""
        anthropic_msgs = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue

            elif msg.role == Role.USER:
                content_parts = []
                for c in msg.content:
                    if isinstance(c, TextContent):
                        content_parts.append({
                            "type": "text",
                            "text": c.text
                        })
                    elif isinstance(c, ImageContent):
                        # Convert from ImageContent to Anthropic format
                        content_parts.append(c.to_anthropic_dict())
                    elif isinstance(c, ToolResponseContent):
                        content_parts.append({
                            "type": "tool_result",
                            "tool_use_id": c.id,
                            "content": str(c.result) if c.result else "Success"
                        })

                anthropic_msgs.append({
                    "role": "user",
                    "content": content_parts if content_parts else [{"type": "text", "text": ""}]
                })

            elif msg.role == Role.ASSISTANT:
                content_parts = []
                for c in msg.content:
                    if isinstance(c, TextContent):
                        content_parts.append({
                            "type": "text",
                            "text": c.text
                        })
                    elif isinstance(c, ToolRequestContent):
                        value = c.tool_call_value
                        if value:
                            content_parts.append({
                                "type": "tool_use",
                                "id": c.id,
                                "name": value.name,
                                "input": value.arguments or {}
                            })

                anthropic_msgs.append({
                    "role": "assistant",
                    "content": content_parts if content_parts else [{"type": "text", "text": ""}]
                })

            elif msg.role == Role.TOOL:
                for c in msg.content:
                    if isinstance(c, ToolResponseContent):
                        content_str = str(c.result) if c.result else "Success"
                        if c.is_error:
                            content_str = f"Error: {content_str}"

                        anthropic_msgs.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": c.id,
                                "content": content_str
                            }]
                        })

        return anthropic_msgs

    def _prepare_tools(self, tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Prepare tools for Anthropic API."""
        if not tools:
            return []

        anthropic_tools = []
        for tool in tools:
            if isinstance(tool, dict):
                anthropic_tools.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", {})
                })
            elif hasattr(tool, "to_dict"):
                tool_dict = tool.to_dict()
                anthropic_tools.append({
                    "name": tool_dict.get("name", ""),
                    "description": tool_dict.get("description", ""),
                    "input_schema": tool_dict.get("input_schema", {})
                })

        return anthropic_tools

    def _handle_error(self, e: Exception):
        """Handle and map exceptions."""
        msg = str(e)

        if isinstance(e, AnthropicAuthError):
            raise AuthenticationError(f"Anthropic Auth Failed: {msg}")
        elif isinstance(e, AnthropicBadRequestError):
            if "context_length" in msg.lower() or "token" in msg.lower():
                raise ContextLengthExceededError(msg)
            raise UsageError(f"Bad Request: {msg}")
        elif isinstance(e, AnthropicConnectionError):
            raise RequestFailedError(f"Connection Failed: {msg}")
        elif isinstance(e, AnthropicRateLimitError):
            raise RequestFailedError(f"Rate Limit: {msg}")
        elif isinstance(e, AnthropicAPIError):
            if "overloaded" in msg.lower():
                raise RequestFailedError(f"Service Overloaded: {msg}")
            raise ExecutionError(f"Anthropic Error: {msg}")
        else:
            raise ExecutionError(f"Unexpected: {msg}")
