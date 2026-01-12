import logging
from typing import Dict, Type, Any, Optional, Union
from .base import BaseLLM, BaseEmbedding, BaseReranker

logger = logging.getLogger("goose.providers.factory")

class ProviderFactory:
    """
    统一的 Provider 工厂类。
    管理 LLM, Embedding, Reranker 的注册与实例化。
    """
    
    # --- 注册表 (Registries) ---
    _llm_registry: Dict[str, Type[BaseLLM]] = {}
    _embedding_registry: Dict[str, Type[BaseEmbedding]] = {}
    _reranker_registry: Dict[str, Type[BaseReranker]] = {}

    # =========================================================
    # 1. LLM Management
    # =========================================================
    
    @classmethod
    def register_llm(cls, name: str):
        """[装饰器] 注册 LLM Provider"""
        def decorator(provider_cls: Type[BaseLLM]):
            if name in cls._llm_registry:
                logger.warning(f"LLM Provider '{name}' already registered. Overwriting.")
            cls._llm_registry[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def create_llm(cls, provider_name: str, config: Dict[str, Any]) -> BaseLLM:
        """根据名称创建 LLM 实例"""
        if provider_name not in cls._llm_registry:
            valid_keys = list(cls._llm_registry.keys())
            raise ValueError(f"Unknown LLM provider '{provider_name}'. Available: {valid_keys}")
        
        try:
            return cls._llm_registry[provider_name](config)
        except Exception as e:
            logger.error(f"Failed to instantiate LLM '{provider_name}': {e}")
            raise e

    # =========================================================
    # 2. Embedding Management
    # =========================================================

    @classmethod
    def register_embedding(cls, name: str):
        """[装饰器] 注册 Embedding Provider"""
        def decorator(provider_cls: Type[BaseEmbedding]):
            if name in cls._embedding_registry:
                logger.warning(f"Embedding Provider '{name}' already registered. Overwriting.")
            cls._embedding_registry[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def create_embedding(cls, provider_name: str, config: Dict[str, Any]) -> BaseEmbedding:
        """根据名称创建 Embedding 实例"""
        if provider_name not in cls._embedding_registry:
            valid_keys = list(cls._embedding_registry.keys())
            raise ValueError(f"Unknown Embedding provider '{provider_name}'. Available: {valid_keys}")
        
        try:
            return cls._embedding_registry[provider_name](config)
        except Exception as e:
            logger.error(f"Failed to instantiate Embedding '{provider_name}': {e}")
            raise e

    # =========================================================
    # 3. Reranker Management
    # =========================================================

    @classmethod
    def register_reranker(cls, name: str):
        """[装饰器] 注册 Reranker Provider"""
        def decorator(provider_cls: Type[BaseReranker]):
            if name in cls._reranker_registry:
                logger.warning(f"Reranker Provider '{name}' already registered. Overwriting.")
            cls._reranker_registry[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def create_reranker(cls, provider_name: str, config: Dict[str, Any]) -> BaseReranker:
        """根据名称创建 Reranker 实例"""
        if provider_name not in cls._reranker_registry:
            valid_keys = list(cls._reranker_registry.keys())
            raise ValueError(f"Unknown Reranker provider '{provider_name}'. Available: {valid_keys}")
        
        try:
            return cls._reranker_registry[provider_name](config)
        except Exception as e:
            logger.error(f"Failed to instantiate Reranker '{provider_name}': {e}")
            raise e

    # =========================================================
    # Utilities
    # =========================================================
    
    @classmethod
    def list_llm_providers(cls) -> list[str]:
        return list(cls._llm_registry.keys())

    @classmethod
    def list_embedding_providers(cls) -> list[str]:
        return list(cls._embedding_registry.keys())

    @classmethod
    def list_reranker_providers(cls) -> list[str]:
        return list(cls._reranker_registry.keys())