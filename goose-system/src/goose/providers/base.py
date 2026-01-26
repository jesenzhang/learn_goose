"""
Provider Base Interfaces

Provider interfaces for LLM, Embedding, and Reranker services.
Reference: goose-rs Provider trait and assistant providers implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Tuple, Any, AsyncGenerator, Optional, Dict
from pydantic import BaseModel, Field
import logging
from ..conversation.message import Message

logger = logging.getLogger("goose.providers.base")


@dataclass
class Usage:
    """
    Usage tracking for LLM calls.

    Reference: Rust Usage struct in goose-rs
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: 'Usage') -> 'Usage':
        """Add two Usage objects together."""
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens
        }


@dataclass
class ProviderUsage:
    """
    Provider usage with model name.

    Reference: Rust ProviderUsage struct in goose-rs
    """
    model: str
    usage: Usage


@dataclass
class ModelConfig:
    """
    Model configuration for providers.

    Reference: goose-rs ModelConfig
    """
    model_name: str = "gpt-4"
    context_limit: int = 128000
    max_output_tokens: int = 4096
    temperature: float = 1.0
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    api_key: Optional[str] = None
    api_key_env: str = "OPENAI_API_KEY"
    base_url: Optional[str] = None
    organization: Optional[str] = None
    project: Optional[str] = None
    timeout: float = 60.0
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def get_inference_config(self) -> 'InferenceConfig':
        return InferenceConfig(
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_output_tokens,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty
        )


@dataclass
class InferenceConfig:
    """
    Inference-time configuration parameters.
    """
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 4096
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    def merge(self, **overrides) -> 'InferenceConfig':
        """Merge with runtime parameters."""
        return InferenceConfig(
            temperature=overrides.get('temperature', self.temperature),
            top_p=overrides.get('top_p', self.top_p),
            max_tokens=overrides.get('max_tokens', self.max_tokens),
            frequency_penalty=overrides.get('frequency_penalty', self.frequency_penalty),
            presence_penalty=overrides.get('presence_penalty', self.presence_penalty)
        )

    def to_api_params(self) -> Dict[str, Any]:
        """Convert to API parameters."""
        params = {}
        if self.temperature != 1.0:
            params['temperature'] = self.temperature
        if self.top_p != 1.0:
            params['top_p'] = self.top_p
        if self.max_tokens:
            params['max_tokens'] = self.max_tokens
        if self.frequency_penalty != 0.0:
            params['frequency_penalty'] = self.frequency_penalty
        if self.presence_penalty != 0.0:
            params['presence_penalty'] = self.presence_penalty
        return params


class BaseLLM(ABC):
    """
    Base interface for LLM providers.

    Reference: goose-rs BaseLLM trait
    """

    @abstractmethod
    async def agenerate(
        self,
        messages: List['Message'],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Tuple['Message', Optional[ProviderUsage]]:
        """
        Asynchronous generate complete response.
        """
        ...

    @abstractmethod
    async def astream(
        self,
        messages: List['Message'],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncGenerator[Tuple['Message', Optional[ProviderUsage]], None]:
        """
        Asynchronous streaming response.
        """
        ...


class BaseEmbedding(ABC):
    """
    Base interface for embedding providers.

    Reference: goose-rs BaseEmbedding trait
    """

    @abstractmethod
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Asynchronous batch embedding."""
        ...

    @abstractmethod
    async def aembed_query(self, text: str) -> List[float]:
        """Asynchronous single query embedding."""
        ...


class BaseReranker(ABC):
    """
    Base interface for reranker providers.
    """

    @abstractmethod
    async def arerank(
        self,
        query: str,
        documents: List['Document'],
        top_k: int = 5
    ) -> List['Document']:
        """Asynchronous reranking."""
        ...


class Provider(BaseLLM, BaseEmbedding):
    """
    Unified Provider interface.

    Combines LLM and Embedding capabilities.
    Reference: goose-rs Provider trait
    """

    def __init__(self, config: ModelConfig):
        self.config = config

    @abstractmethod
    def get_model_config(self) -> ModelConfig:
        """Get model configuration."""
        ...

    @abstractmethod
    async def agenerate(
        self,
        messages: List['Message'],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Tuple['Message', Optional[ProviderUsage]]:
        """Asynchronous generate complete response."""
        ...

    @abstractmethod
    async def astream(
        self,
        messages: List['Message'],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncGenerator[Tuple['Message', Optional[ProviderUsage]], None]:
        """Asynchronous streaming response."""
        ...

    @abstractmethod
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Asynchronous batch embedding."""
        ...

    @abstractmethod
    async def aembed_query(self, text: str) -> List[float]:
        """Asynchronous single query embedding."""
        ...


class Document(BaseModel):
    """
    Document for reranking.
    """
    page_content: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """
    Tool definition for LLM calls.
    Reference: OpenAI function calling format
    """
    type: str = "function"
    function: Dict[str, Any]


class ProviderMetadata(BaseModel):
    """
    Provider metadata.
    Reference: goose-rs ProviderMetadata
    """
    name: str
    version: str = "1.0.0"
    capabilities: List[str] = Field(default_factory=list)


# Forward references for type hints (resolved at runtime)
Message = None
