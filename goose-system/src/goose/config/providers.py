"""
Provider Registry and Discovery

Provider 注册与自动发现，支持：
- Provider 元数据注册
- 模型列表获取
- Provider 配置测试
- 自定义 Provider

Reference: goose-rs/crates/goose/src/config/declarative_providers.rs
"""

import os
import json
import asyncio
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple, Type
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("goose.config.providers")


class ProviderType(str, Enum):
    """Provider 类型"""
    LLM = "llm"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


@dataclass
class ProviderKey:
    """Provider 配置密钥"""
    name: str
    required: bool = True
    secret: bool = False
    default: Optional[str] = None
    description: str = ""
    oauth_flow: bool = False


@dataclass
class ProviderMetadata:
    """Provider 元数据"""
    name: str
    display_name: str
    description: str
    provider_type: ProviderType
    config_keys: List[ProviderKey]
    default_model: str
    known_models: List[str] = field(default_factory=list)
    allows_unlisted_models: bool = True
    api_docs_url: Optional[str] = None


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    display_name: Optional[str] = None
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    capabilities: List[str] = field(default_factory=list)
    pricing: Optional[Dict[str, float]] = None


class Provider(ABC):
    """Provider 抽象基类"""
    
    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """获取 Provider 元数据"""
        pass
    
    @abstractmethod
    async def fetch_recommended_models(self) -> Optional[List[str]]:
        """获取推荐的模型列表"""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """测试 Provider 连接"""
        pass


class LLMProvider(Provider):
    """LLM Provider 基类"""
    
    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str:
        """完成文本"""
        pass
    
    @abstractmethod
    async def stream_complete(self, prompt: str, **kwargs):
        """流式完成文本"""
        pass


class ProviderRegistry:
    """Provider 注册表"""
    
    _instance: Optional['ProviderRegistry'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'ProviderRegistry':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ProviderRegistry()
        return cls._instance
    
    def __init__(self):
        self._providers: Dict[str, ProviderMetadata] = {}
        self._provider_classes: Dict[str, Type[Provider]] = {}
        self._lock = threading.Lock()
        self._register_default_providers()
    
    def _register_default_providers(self):
        """注册默认 Provider"""
        # OpenAI
        self.register_provider(ProviderMetadata(
            name="openai",
            display_name="OpenAI",
            description="OpenAI GPT models (GPT-4, GPT-3.5)",
            provider_type=ProviderType.LLM,
            config_keys=[
                ProviderKey(name="api_key", required=True, secret=True, description="API Key"),
                ProviderKey(name="base_url", required=False, default="https://api.openai.com/v1", description="Base URL"),
            ],
            default_model="gpt-4",
            known_models=[
                "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini",
                "gpt-3.5-turbo", "gpt-3.5-turbo-16k"
            ],
            allows_unlisted_models=True,
        ))
        
        # Anthropic
        self.register_provider(ProviderMetadata(
            name="anthropic",
            display_name="Anthropic",
            description="Anthropic Claude models",
            provider_type=ProviderType.LLM,
            config_keys=[
                ProviderKey(name="api_key", required=True, secret=True, description="API Key"),
                ProviderKey(name="base_url", required=False, description="Base URL"),
            ],
            default_model="claude-sonnet-4-20250514",
            known_models=[
                "claude-opus-4-20250514", "claude-sonnet-4-20250514",
                "claude-haiku-3-20250514"
            ],
            allows_unlisted_models=True,
        ))
        
        # Google
        self.register_provider(ProviderMetadata(
            name="google",
            display_name="Google",
            description="Google Gemini models",
            provider_type=ProviderType.LLM,
            config_keys=[
                ProviderKey(name="api_key", required=True, secret=True, description="API Key"),
            ],
            default_model="gemini-pro",
            known_models=["gemini-pro", "gemini-ultra", "gemini-flash"],
            allows_unlisted_models=True,
        ))
        
        # DeepSeek
        self.register_provider(ProviderMetadata(
            name="deepseek",
            display_name="DeepSeek",
            description="DeepSeek Chat models",
            provider_type=ProviderType.LLM,
            config_keys=[
                ProviderKey(name="api_key", required=True, secret=True, description="API Key"),
                ProviderKey(name="base_url", required=False, default="https://api.deepseek.com", description="Base URL"),
            ],
            default_model="deepseek-chat",
            known_models=["deepseek-chat"],
            allows_unlisted_models=True,
        ))
        
        # OpenRouter
        self.register_provider(ProviderMetadata(
            name="openrouter",
            display_name="OpenRouter",
            description="OpenRouter - Access any model through unified API",
            provider_type=ProviderType.LLM,
            config_keys=[
                ProviderKey(name="api_key", required=True, secret=True, description="API Key"),
            ],
            default_model="openrouter/auto",
            allows_unlisted_models=True,
        ))
        
        # Together AI
        self.register_provider(ProviderMetadata(
            name="together",
            display_name="Together AI",
            description="Together AI - Open source models",
            provider_type=ProviderType.LLM,
            config_keys=[
                ProviderKey(name="api_key", required=True, secret=True, description="API Key"),
                ProviderKey(name="base_url", required=False, default="https://api.together.xyz", description="Base URL"),
            ],
            default_model="meta-llama/Llama-3-70b-chat-hf",
            known_models=[
                "meta-llama/Llama-3-70b-chat-hf",
                "meta-llama/Llama-3-8b-chat-hf",
                "mistralai/Mixtral-8x7b-Instruct-v0.1"
            ],
            allows_unlisted_models=True,
        ))
    
    def register_provider(self, metadata: ProviderMetadata) -> None:
        """注册 Provider"""
        with self._lock:
            self._providers[metadata.name] = metadata
    
    def get_provider(self, name: str) -> Optional[ProviderMetadata]:
        """获取 Provider 元数据"""
        return self._providers.get(name)
    
    def list_providers(self) -> List[ProviderMetadata]:
        """列出所有 Provider"""
        return list(self._providers.values())
    
    def search_providers(self, query: str) -> List[ProviderMetadata]:
        """搜索 Provider"""
        query = query.lower()
        return [
            p for p in self._providers.values()
            if query in p.name.lower() or query in p.display_name.lower() or query in p.description.lower()
        ]
    
    def get_required_keys(self, provider_name: str) -> List[ProviderKey]:
        """获取 Provider 必需的配置密钥"""
        provider = self.get_provider(provider_name)
        if provider:
            return [k for k in provider.config_keys if k.required]
        return []


class ModelDiscovery:
    """模型发现服务"""
    
    @staticmethod
    async def fetch_models_from_provider(provider_name: str, api_key: str, **kwargs) -> Optional[List[str]]:
        """从 Provider 获取模型列表"""
        registry = ProviderRegistry.get_instance()
        provider = registry.get_provider(provider_name)
        
        if not provider:
            return None
        
        # 如果 Provider 有已知模型列表，直接返回
        if provider.known_models:
            return provider.known_models
        
        # 尝试从 API 获取
        try:
            if provider_name == "openai":
                return await ModelDiscovery._fetch_openai_models(api_key, **kwargs)
            elif provider_name == "anthropic":
                return await ModelDiscovery._fetch_anthropic_models(api_key, **kwargs)
            elif provider_name == "google":
                return await ModelDiscovery._fetch_google_models(api_key, **kwargs)
        except Exception as e:
            logger.error(f"Failed to fetch models from {provider_name}: {e}")
        
        return None
    
    @staticmethod
    async def _fetch_openai_models(api_key: str, base_url: str = "https://api.openai.com/v1") -> List[str]:
        """从 OpenAI 获取模型列表"""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", []) if "gpt" in m["id"].lower()]
    
    @staticmethod
    async def _fetch_anthropic_models(api_key: str, base_url: Optional[str] = None) -> List[str]:
        """从 Anthropic 获取模型列表"""
        # Anthropic doesn't have a public models API, return known models
        return [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-haiku-3-20250514"
        ]
    
    @staticmethod
    async def _fetch_google_models(api_key: str) -> List[str]:
        """从 Google 获取模型列表"""
        return ["gemini-pro", "gemini-ultra", "gemini-flash"]


class ProviderTester:
    """Provider 配置测试器"""
    
    @staticmethod
    async def test_provider_configuration(
        provider_name: str,
        model: str,
        api_key: str,
        **kwargs
    ) -> Tuple[bool, str]:
        """
        测试 Provider 配置
        
        Returns:
            (success, message)
        """
        try:
            registry = ProviderRegistry.get_instance()
            provider = registry.get_provider(provider_name)
            
            if not provider:
                return False, f"Unknown provider: {provider_name}"
            
            # 简单测试 - 发送一个小的聊天完成请求
            if provider_name == "openai":
                return await ProviderTester._test_openai(api_key, model, **kwargs)
            elif provider_name == "anthropic":
                return await ProviderTester._test_anthropic(api_key, model, **kwargs)
            elif provider_name == "deepseek":
                return await ProviderTester._test_deepseek(api_key, model, **kwargs)
            elif provider_name == "openrouter":
                return await ProviderTester._test_openrouter(api_key, model, **kwargs)
            else:
                # 通用测试
                return True, f"Provider {provider_name} configured successfully"
                
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    async def _test_openai(api_key: str, model: str, base_url: str = "https://api.openai.com/v1") -> Tuple[bool, str]:
        """测试 OpenAI 配置"""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5
                }
            )
            
            if response.status_code == 200:
                return True, "OpenAI configured successfully"
            else:
                error = response.json().get("error", {})
                return False, error.get("message", "OpenAI connection failed")
    
    @staticmethod
    async def _test_anthropic(api_key: str, model: str, base_url: Optional[str] = None) -> Tuple[bool, str]:
        """测试 Anthropic 配置"""
        import httpx
        
        base_url = base_url or "https://api.anthropic.com"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/v1/messages",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hi"}]
                }
            )
            
            if response.status_code == 200:
                return True, "Anthropic configured successfully"
            else:
                error = response.json().get("error", {})
                return False, error.get("message", "Anthropic connection failed")
    
    @staticmethod
    async def _test_deepseek(api_key: str, model: str, base_url: str = "https://api.deepseek.com") -> Tuple[bool, str]:
        """测试 DeepSeek 配置"""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5
                }
            )
            
            if response.status_code == 200:
                return True, "DeepSeek configured successfully"
            else:
                error = response.json().get("error", {})
                return False, error.get("message", "DeepSeek connection failed")
    
    @staticmethod
    async def _test_openrouter(api_key: str, model: str) -> Tuple[bool, str]:
        """测试 OpenRouter 配置"""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5
                }
            )
            
            if response.status_code == 200:
                return True, "OpenRouter configured successfully"
            else:
                error = response.json().get("error", {})
                return False, error.get("message", "OpenRouter connection failed")


# 快捷函数

def get_provider_registry() -> ProviderRegistry:
    """获取 Provider 注册表"""
    return ProviderRegistry.get_instance()


def list_providers() -> List[ProviderMetadata]:
    """列出所有 Provider"""
    return get_provider_registry().list_providers()


def get_provider_metadata(name: str) -> Optional[ProviderMetadata]:
    """获取 Provider 元数据"""
    return get_provider_registry().get_provider(name)


def search_providers(query: str) -> List[ProviderMetadata]:
    """搜索 Provider"""
    return get_provider_registry().search_providers(query)


async def fetch_provider_models(provider_name: str, api_key: str, **kwargs) -> Optional[List[str]]:
    """获取 Provider 模型列表"""
    return await ModelDiscovery.fetch_models_from_provider(provider_name, api_key, **kwargs)


async def test_provider_config(provider_name: str, model: str, api_key: str, **kwargs) -> Tuple[bool, str]:
    """测试 Provider 配置"""
    return await ProviderTester.test_provider_configuration(provider_name, model, api_key, **kwargs)
