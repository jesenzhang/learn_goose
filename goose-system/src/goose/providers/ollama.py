"""
Ollama Provider

Ollama 本地大语言模型 provider。
支持本地部署的 LLM 模型。

Reference: https://github.com/ollama/ollama/blob/main/docs/api.md
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

logger = logging.getLogger("goose.providers.ollama")

OLLAMA_DEFAULT_MODELS = {
    "llama3.2": 128000,
    "llama3.1": 128000,
    "llama3": 8192,
    "llama2": 4096,
    "mistral": 32768,
    "mixtral": 32768,
    "codellama": 16384,
    "deepseek-coder": 32768,
    "qwen2.5-coder": 32768,
}


@ProviderFactory.register_llm("ollama")
class OllamaProvider:
    """
    Ollama Provider for local LLM models.
    
    Features:
    - Local model inference
    - Streaming responses
    - Tool calling (with compatible models)
    - Embeddings support
    """

    def __init__(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            raise TypeError("config must be a dict")
        
        self.model_name = config.get("model_name", "llama3.2")
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.timeout = config.get("timeout", 120.0)
        
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )

        logger.info(f"Ollama Provider initialized: model={self.model_name}, url={self.base_url}")

        self.inference_config = self._build_inference_config(config)
        self._sem = asyncio.Semaphore(10)

    def _build_inference_config(self, config: Dict[str, Any]) -> "InferenceConfig":
        """构建推理配置"""
        temperature = config.get("temperature", 0.7)
        max_tokens = config.get("max_tokens", 4096)
        top_p = config.get("top_p", 0.9)
        
        return InferenceConfig(
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )

    def get_model_config(self) -> "ModelConfig":
        """获取模型配置"""
        context_limit = OLLAMA_DEFAULT_MODELS.get(
            self.model_name.split(":")[0] if ":" in self.model_name else self.model_name,
            16384
        )
        return ModelConfig(
            model_name=self.model_name,
            context_limit=context_limit,
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
        from goose.providers.base import Usage, ProviderUsage

        prompt = self._build_prompt(messages)
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.inference_config.temperature,
                "num_predict": self.inference_config.max_tokens,
                "top_k": 40,
                "top_p": self.inference_config.top_p,
            }
        }

        if stop:
            payload["options"]["stop"] = stop

        if tools:
            payload["format"] = "json"
        
        async with self._sem:
            try:
                response = await self._post("/api/generate", payload)
                
                response_data = response.json()
                
                content_text = response_data.get("response", "")
                
                message = Message(
                    role=Role.ASSISTANT,
                    content=[TextContent(text=content_text)]
                )

                eval_count = response_data.get("eval_count", 0)
                eval_duration = response_data.get("eval_duration", 0) / 1e9
                
                usage = ProviderUsage(
                    model=self.model_name,
                    usage=Usage(
                        input_tokens=response_data.get("prompt_eval_count", 0),
                        output_tokens=eval_count,
                        total_tokens=response_data.get("prompt_eval_count", 0) + eval_count,
                        duration_seconds=eval_duration
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
        from goose.providers.base import Usage, ProviderUsage

        prompt = self._build_prompt(messages)
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.inference_config.temperature,
                "num_predict": self.inference_config.max_tokens,
            }
        }

        async with self._sem:
            try:
                async with self.http_client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                message = Message(
                                    role=Role.ASSISTANT,
                                    content=[TextContent(text=chunk)]
                                )
                                yield message, None
                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                self._handle_error(e)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """生成文档嵌入"""
        embeddings = []
        
        async with self._sem:
            for text in texts:
                payload = {
                    "model": self.model_name,
                    "prompt": text,
                }
                
                try:
                    response = await self._post("/api/embeddings", payload)
                    data = response.json()
                    embedding = data.get("embedding", [])
                    embeddings.append(embedding)
                except Exception as e:
                    logger.error(f"Embedding failed: {e}")
                    embeddings.append([0.0] * 4096)
        
        return embeddings

    async def aembed_query(self, text: str) -> List[float]:
        """生成查询嵌入"""
        results = await self.aembed_documents([text])
        return results[0] if results else [0.0] * 4096

    def _build_prompt(self, messages: List["Message"]) -> str:
        """构建 Ollama 格式的提示"""
        prompt_parts = []
        
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            content = msg.text or ""
            
            if isinstance(content, list):
                for c in content:
                    if hasattr(c, 'text'):
                        content = c.text
                        break
            
            prompt_parts.append(f"[{role}] {content}")
        
        return "\n".join(prompt_parts)

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> httpx.Response:
        """发送 POST 请求"""
        url = f"{self.base_url}{endpoint}"
        response = await self.http_client.post(url, json=payload)
        response.raise_for_status()
        return response

    async def aclose(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()

    def _handle_error(self, e: Exception):
        """处理错误"""
        error_str = str(e)
        
        if "connection" in error_str.lower():
            from goose.providers.base import RequestFailedError
            raise RequestFailedError(f"Ollama connection failed: {e}")
        elif "timeout" in error_str.lower():
            from goose.providers.base import RequestFailedError
            raise RequestFailedError(f"Ollama timeout: {e}")
        else:
            from goose.providers.base import ExecutionError
            raise ExecutionError(f"Ollama error: {e}")

    @property
    def available_models(self) -> List[str]:
        """获取可用模型列表"""
        return list(OLLAMA_DEFAULT_MODELS.keys())


class OllamaEmbeddingProvider:
    """Ollama 专用嵌入 provider"""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0
    ):
        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout
        
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0)
        )

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """生成文档嵌入"""
        embeddings = []
        
        for text in texts:
            payload = {
                "model": self.model_name,
                "prompt": text,
            }
            
            try:
                response = await self.http_client.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload
                )
                data = response.json()
                embeddings.append(data.get("embedding", []))
            except Exception as e:
                logger.error(f"Embedding failed for text: {e}")
                embeddings.append([])
        
        return embeddings

    async def aembed_query(self, text: str) -> List[float]:
        """生成查询嵌入"""
        results = await self.aembed_documents([text])
        return results[0] if results else []

    async def aclose(self):
        """关闭客户端"""
        await self.http_client.aclose()


async def list_ollama_models(base_url: str = "http://localhost:11434") -> List[Dict[str, Any]]:
    """
    列出 Ollama 可用模型
    
    Args:
        base_url: Ollama 服务器地址
        
    Returns:
        模型列表
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/api/tags")
            data = response.json()
            
            models = []
            for model in data.get("models", []):
                models.append({
                    "name": model.get("name", ""),
                    "size": model.get("size", 0),
                    "digest": model.get("digest", ""),
                    "modified_at": model.get("modified_at", ""),
                })
            
            return models
    except Exception as e:
        logger.error(f"Failed to list Ollama models: {e}")
        return []


def ollama_model_info(model_name: str) -> Dict[str, Any]:
    """获取 Ollama 模型信息"""
    base_name = model_name.split(":")[0] if ":" in model_name else model_name
    return {
        "name": model_name,
        "context_limit": OLLAMA_DEFAULT_MODELS.get(base_name, 16384),
        "supports_tools": False,
        "supports_streaming": True,
        "supports_embeddings": True,
    }
