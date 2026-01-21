"""
Provider Factory

Factory pattern for registering and creating providers.
Reference: assistant providers factory implementation.
"""

import logging
from typing import Dict, Type, Any, Optional
from .base import BaseLLM, BaseEmbedding, BaseReranker

logger = logging.getLogger("goose.providers.factory")


class ProviderFactory:
    """
    Unified Provider Factory.

    Manages registration and instantiation of LLM, Embedding, and Reranker providers.
    Reference: assistant ProviderFactory
    """

    _llm_registry: Dict[str, Type[BaseLLM]] = {}
    _embedding_registry: Dict[str, Type[BaseEmbedding]] = {}
    _reranker_registry: Dict[str, Type[BaseReranker]] = {}

    @classmethod
    def register_llm(cls, name: str):
        """Decorator for registering LLM provider."""
        def decorator(provider_cls: Type[BaseLLM]):
            if name in cls._llm_registry:
                logger.warning(f"LLM Provider '{name}' already registered. Overwriting.")
            cls._llm_registry[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def create_llm(cls, provider_name: str, config: Dict[str, Any]) -> BaseLLM:
        """Create LLM instance by name."""
        if provider_name not in cls._llm_registry:
            valid_keys = list(cls._llm_registry.keys())
            raise ValueError(f"Unknown LLM provider '{provider_name}'. Available: {valid_keys}")

        try:
            return cls._llm_registry[provider_name](config)
        except Exception as e:
            logger.error(f"Failed to instantiate LLM '{provider_name}': {e}")
            raise e

    @classmethod
    def register_embedding(cls, name: str):
        """Decorator for registering Embedding provider."""
        def decorator(provider_cls: Type[BaseEmbedding]):
            if name in cls._embedding_registry:
                logger.warning(f"Embedding Provider '{name}' already registered. Overwriting.")
            cls._embedding_registry[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def create_embedding(cls, provider_name: str, config: Dict[str, Any]) -> BaseEmbedding:
        """Create Embedding instance by name."""
        if provider_name not in cls._embedding_registry:
            valid_keys = list(cls._embedding_registry.keys())
            raise ValueError(f"Unknown Embedding provider '{provider_name}'. Available: {valid_keys}")

        try:
            return cls._embedding_registry[provider_name](config)
        except Exception as e:
            logger.error(f"Failed to instantiate Embedding '{provider_name}': {e}")
            raise e

    @classmethod
    def register_reranker(cls, name: str):
        """Decorator for registering Reranker provider."""
        def decorator(provider_cls: Type[BaseReranker]):
            if name in cls._reranker_registry:
                logger.warning(f"Reranker Provider '{name}' already registered. Overwriting.")
            cls._reranker_registry[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def create_reranker(cls, provider_name: str, config: Dict[str, Any]) -> BaseReranker:
        """Create Reranker instance by name."""
        if provider_name not in cls._reranker_registry:
            valid_keys = list(cls._reranker_registry.keys())
            raise ValueError(f"Unknown Reranker provider '{provider_name}'. Available: {valid_keys}")

        try:
            return cls._reranker_registry[provider_name](config)
        except Exception as e:
            logger.error(f"Failed to instantiate Reranker '{provider_name}': {e}")
            raise e

    @classmethod
    def list_llm_providers(cls) -> list[str]:
        """List available LLM providers."""
        return list(cls._llm_registry.keys())

    @classmethod
    def list_embedding_providers(cls) -> list[str]:
        """List available Embedding providers."""
        return list(cls._embedding_registry.keys())

    @classmethod
    def list_reranker_providers(cls) -> list[str]:
        """List available Reranker providers."""
        return list(cls._reranker_registry.keys())
