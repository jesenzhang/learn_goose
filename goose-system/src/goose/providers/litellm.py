"""
LiteLLM Provider

LiteLLM 统一接口 provider，支持 100+ LLM API。
支持 OpenAI, Anthropic, Azure, VertexAI, Bedrock, Cohere, etc.

Reference: https://docs.litellm.ai/docs/
"""

import os
import json
import logging
import asyncio
import uuid
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple

import httpx

from .base import ModelConfig, InferenceConfig, Usage, ProviderUsage
from .factory import ProviderFactory

logger = logging.getLogger("goose.providers.litellm")

LITELLM_DEFAULT_MODELS = {
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-3.5-turbo": 16385,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "gemini-pro": 1048576,
    "gemini-1.5-pro": 2000000,
    "command-r": 128000,
    "command-r-plus": 128000,
}


@ProviderFactory.register_llm("litellm")
class LiteLLMProvider:
    """
    LiteLLM Unified Provider.
    
    Features:
    - 100+ LLM models support
    - Unified API interface
    - Cost tracking
    - Retry logic
    - Fallback models
    """

    def __init__(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            raise TypeError("config must be a dict")
        
        self.model_name = config.get("model_name", "gpt-3.5-turbo")
        self.api_key = config.get("api_key") or os.getenv("LITELLM_API_KEY")
        self.base_url = config.get("base_url") or os.getenv("LITELLM_BASE_URL")
        
        self.timeout = config.get("timeout", 60.0)
        self.max_retries = config.get("max_retries", 3)
        
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
        )

        logger.info(f"LiteLLM Provider initialized: model={self.model_name}")

        self.inference_config = self._build_inference_config(config)
        self._sem = asyncio.Semaphore(50)

    def _build_inference_config(self, config: Dict[str, Any]) -> "InferenceConfig":
        return InferenceConfig(
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 4096),
            top_p=config.get("top_p", 0.9),
            presence_penalty=config.get("presence_penalty", 0),
            frequency_penalty=config.get("frequency_penalty", 0),
        )

    def get_model_config(self) -> "ModelConfig":
        context_limit = LITELLM_DEFAULT_MODELS.get(self.model_name, 4096)
        return ModelConfig(
            model_name=self.model_name,
            context_limit=context_limit,
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def agenerate(
        self,
        messages: List["Message"],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Tuple["Message", Optional["ProviderUsage"]]:
        """生成完整响应"""
        from goose.conversation.message import Role, TextContent, ToolRequestContent

        payload = self._build_payload(messages, tools, stop)

        async with self._sem:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await self._post("/completion", payload)
                    data = response.json()
                    
                    choice = data.get("choices", [{}])[0]
                    message_data = choice.get("message", {})
                    
                    content_parts = []
                    if "content" in message_data and message_data["content"]:
                        content_parts.append(TextContent(text=message_data["content"]))

                    if "tool_calls" in message_data:
                        for tool_call in message_data["tool_calls"]:
                            tc = tool_call.get("function", {})
                            # Parse arguments - could be string or already parsed dict
                            args = tc.get("arguments", "{}")
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    args = {}
                            content_parts.append(ToolRequestContent.create(
                                tool_id=tool_call.get("id", str(uuid.uuid4())),
                                name=tc.get("name", ""),
                                arguments=args
                            ))

                    message = Message(
                        role=Role.ASSISTANT,
                        content=content_parts
                    )

                    usage = None
                    if "usage" in data:
                        usage_data = data["usage"]
                        usage = ProviderUsage(
                            model=self.model_name,
                            usage=Usage(
                                input_tokens=usage_data.get("prompt_tokens", 0),
                                output_tokens=usage_data.get("completion_tokens", 0),
                                total_tokens=usage_data.get("total_tokens", 0)
                            )
                        )

                    return message, usage

                except Exception as e:
                    if attempt == self.max_retries:
                        raise
                    await asyncio.sleep(2 ** attempt)

    async def astream(
        self,
        messages: List["Message"],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncGenerator[Tuple["Message", Optional["ProviderUsage"]], None]:
        """流式生成响应"""
        from goose.providers.message import Role, TextContent

        payload = self._build_payload(messages, tools, stop)
        payload["stream"] = True

        async with self._sem:
            try:
                async with self.http_client.stream("POST", f"{self.base_url}/completion", json=payload) as response:
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                message = Message(
                                    role=Role.ASSISTANT,
                                    content=[TextContent(text=content)]
                                )
                                yield message, None
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                self._handle_error(e)

    def _build_payload(
        self,
        messages: List["Message"],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """构建请求 payload"""
        from goose.conversation.message import ToolRequestContent, ToolResponseContent

        messages_data = []
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)

            content_parts = []
            for c in msg.content:
                # Check if this is text content
                if isinstance(c, TextContent):
                    content_parts.append(c.text)
                # Check if this is tool response content
                elif isinstance(c, ToolResponseContent):
                    content_parts.append({
                        "type": "tool_result",
                        "tool_use_id": c.id,
                        "content": json.dumps(c.content) if c.content else "Success"
                    })
                # Check if this is tool request content
                elif isinstance(c, ToolRequestContent):
                    value = c.tool_call_value
                    if value:
                        content_parts.append({
                            "type": "tool_use",
                            "id": c.id,
                            "function": {
                                "name": value.name,
                                "arguments": json.dumps(value.arguments or {})
                            }
                        })

            msg_data = {"role": role, "content": "\n".join(str(c) for c in content_parts)}
            messages_data.append(msg_data)

        payload = {
            "model": self.model_name,
            "messages": messages_data,
            "temperature": self.inference_config.temperature,
            "max_tokens": self.inference_config.max_tokens,
            "top_p": self.inference_config.top_p,
        }

        if stop:
            payload["stop"] = stop

        if tools:
            payload["tools"] = tools

        return payload

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> httpx.Response:
        """发送 POST 请求"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        url = f"{self.base_url}{endpoint}"
        response = await self.http_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response

    async def aclose(self):
        """关闭客户端"""
        await self.http_client.aclose()

    def _handle_error(self, e: Exception):
        """处理错误"""
        from goose.providers.base import ExecutionError
        raise ExecutionError(f"LiteLLM error: {e}")

    @property
    def available_models(self) -> List[str]:
        """获取可用模型列表"""
        return list(LITELLM_DEFAULT_MODELS.keys())


def litellm_model_info(model_name: str) -> Dict[str, Any]:
    """获取 LiteLLM 模型信息"""
    return {
        "name": model_name,
        "context_limit": LITELLM_DEFAULT_MODELS.get(model_name, 4096),
        "supports_tools": True,
        "supports_streaming": True,
    }
