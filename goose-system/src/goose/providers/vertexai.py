"""
VertexAI Provider

Google VertexAI provider，支持 Gemini 系列模型。

Reference: https://cloud.google.com/vertexai/docs/generative-ai/docs/reference/python
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

logger = logging.getLogger("goose.providers.vertexai")

VERTEXAI_DEFAULT_MODELS = {
    "gemini-1.0-pro": 1048576,
    "gemini-1.0-pro-vision": 1048576,
    "gemini-1.5-pro": 2000000,
    "gemini-1.5-flash": 1000000,
    "gemini-pro": 1048576,
    "gemini-ultra": 2000000,
}


@ProviderFactory.register_llm("vertexai")
class VertexAIProvider:
    """
    Google VertexAI Provider for Gemini models.
    
    Features:
    - Gemini Pro/Ultra models
    - Multimodal support
    - Function calling
    - JSON mode
    """

    def __init__(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            raise TypeError("config must be a dict")
        
        self.model_name = config.get("model_name", "gemini-1.5-pro")
        self.project_id = config.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
        self.location = config.get("location", "us-central1")
        self.api_key = config.get("api_key") or os.getenv("GOOGLE_API_KEY")
        
        self.timeout = config.get("timeout", 120.0)
        
        self.base_url = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{self.model_name}:generateContent"
        
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )

        logger.info(f"VertexAI Provider initialized: model={self.model_name}")

        self.inference_config = self._build_inference_config(config)
        self._sem = asyncio.Semaphore(30)

    def _build_inference_config(self, config: Dict[str, Any]) -> "InferenceConfig":
        return InferenceConfig(
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 8192),
            top_p=config.get("top_p", 0.95),
            top_k=config.get("top_k", 40),
        )

    def get_model_config(self) -> "ModelConfig":
        context_limit = VERTEXAI_DEFAULT_MODELS.get(self.model_name, 1048576)
        return ModelConfig(
            model_name=self.model_name,
            context_limit=context_limit
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

        payload = self._build_payload(messages, tools)

        async with self._sem:
            try:
                response = await self._post(payload)
                data = response.json()
                
                candidates = data.get("candidates", [])
                if not candidates:
                    from goose.providers.base import ExecutionError
                    raise ExecutionError("No response from VertexAI")
                
                candidate = candidates[0]
                content = candidate.get("content", {})
                parts = content.get("parts", [])

                content_parts = []
                for part in parts:
                    if "text" in part:
                        content_parts.append(TextContent(text=part["text"]))
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        content_parts.append(ToolRequestContent.create(
                            tool_id=fc.get("id", str(uuid.uuid4())),
                            name=fc.get("name", ""),
                            arguments=fc.get("args", {})
                        ))

                message = Message(
                    role=Role.ASSISTANT,
                    content=content_parts
                )

                usage = None
                if "usageMetadata" in data:
                    usage_data = data["usageMetadata"]
                    usage = ProviderUsage(
                        model=self.model_name,
                        usage=Usage(
                            input_tokens=usage_data.get("promptTokenCount", 0),
                            output_tokens=usage_data.get("candidatesTokenCount", 0),
                            total_tokens=usage_data.get("totalTokenCount", 0)
                        )
                    )

                return message, usage

            except Exception as e:
                self._handle_error(e)

    async def astream(
        self,
        messages: List["Message"],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncGenerator[Tuple["Message", Optional["ProviderUsage"]], None]:
        """流式生成响应"""
        from goose.providers.message import Role, TextContent

        payload = self._build_payload(messages, tools)
        payload["generationConfig"] = {"stream": True}

        async with self.http_client.stream("POST", self.base_url, json=payload) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    candidates = data.get("candidates", [])
                    if candidates:
                        candidate = candidates[0]
                        content = candidate.get("content", {})
                        parts = content.get("parts", [])
                        
                        for part in parts:
                            if "text" in part:
                                message = Message(
                                    role=Role.ASSISTANT,
                                    content=[TextContent(text=part["text"])]
                                )
                                yield message, None
                except json.JSONDecodeError:
                    continue

    def _build_payload(
        self,
        messages: List["Message"],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """构建请求 payload"""
        contents = []
        
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            role = "user" if role == "user" else "model" if role == "assistant" else role
            
            parts = []
            for c in msg.content:
                if hasattr(c, 'text'):
                    parts.append({"text": c.text})
                elif hasattr(c, 'tool_call_id'):
                    parts.append({
                        "functionResponse": {
                            "name": getattr(c, 'name', ''),
                            "response": {"result": str(c.result or "")}
                        }
                    })
            
            contents.append({"role": role, "parts": parts})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.inference_config.temperature,
                "maxOutputTokens": self.inference_config.max_tokens,
                "topP": self.inference_config.top_p,
                "topK": getattr(self.inference_config, 'top_k', 40),
            }
        }

        if tools:
            functions = []
            for tool in tools:
                functions.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                })
            payload["tools"] = [{"functionDeclarations": functions}]

        return payload

    async def _post(self, payload: Dict[str, Any]) -> httpx.Response:
        """发送 POST 请求"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        
        response = await self.http_client.post(self.base_url, json=payload, headers=headers)
        response.raise_for_status()
        return response

    async def aclose(self):
        """关闭客户端"""
        await self.http_client.aclose()

    def _handle_error(self, e: Exception):
        """处理错误"""
        from goose.providers.base import ExecutionError, RequestFailedError
        
        error_str = str(e)
        if "429" in error_str or "rate" in error_str.lower():
            raise RequestFailedError(f"VertexAI rate limit: {e}")
        elif "404" in error_str or "not found" in error_str.lower():
            raise ExecutionError(f"VertexAI model not found: {e}")
        else:
            raise ExecutionError(f"VertexAI error: {e}")

    @property
    def available_models(self) -> List[str]:
        """获取可用模型列表"""
        return list(VERTEXAI_DEFAULT_MODELS.keys())


def vertexai_model_info(model_name: str) -> Dict[str, Any]:
    """获取 VertexAI 模型信息"""
    return {
        "name": model_name,
        "context_limit": VERTEXAI_DEFAULT_MODELS.get(model_name, 1048576),
        "supports_tools": True,
        "supports_streaming": True,
        "supports_multimodal": True,
    }
