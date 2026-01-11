import logging
from typing import Dict, Type, Any, Optional, Union
from .base import BaseLLM, BaseEmbedding, BaseReranker

logger = logging.getLogger("goose.providers.factory")

class ProviderFactory:
    """
    统一的 Provider 工厂类。
    管理 LLM, Embedding, Reranker 的注册与实例化。
    支持连接池复用。
    """

    # --- 注册表 (Registries) ---
    _llm_registry: Dict[str, Type[BaseLLM]] = {}
    _embedding_registry: Dict[str, Type[BaseEmbedding]] = {}
    _reranker_registry: Dict[str, Type[BaseReranker]] = {}

    # --- 连接池 (Connection Pools) ---
    _llm_pool: Dict[str, BaseLLM] = {}
    _embedding_pool: Dict[str, BaseEmbedding] = {}
    _reranker_pool: Dict[str, BaseReranker] = {}
    _pool_enabled: bool = True

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
    def create_llm(cls, provider_name: str, config: Any, use_pool: bool = True) -> BaseLLM:
        """
        根据名称创建或复用 LLM 实例

        Args:
            provider_name: Provider 类型名称
            config: 配置对象 (ModelConfig 或 dict)
            use_pool: 是否使用连接池复用实例

        Returns:
            LLM 实例
        """
        if provider_name not in cls._llm_registry:
            valid_keys = list(cls._llm_registry.keys())
            raise ValueError(f"Unknown LLM provider '{provider_name}'. Available: {valid_keys}")

        # 转换 config 为 dict 以便生成 cache key
        if hasattr(config, 'model_dump'):
            config_dict = config.model_dump()
        elif isinstance(config, dict):
            config_dict = config
        else:
            config_dict = {"model_name": str(config)}

        # 生成 pool key
        pool_key = f"{provider_name}:{config_dict.get('model_name', 'default')}"

        # 检查连接池
        if use_pool and cls._pool_enabled and pool_key in cls._llm_pool:
            logger.debug(f"Reusing LLM from pool: {pool_key}")
            return cls._llm_pool[pool_key]

        # 创建新实例
        try:
            llm = cls._llm_registry[provider_name](config_dict)
            if use_pool and cls._pool_enabled:
                cls._llm_pool[pool_key] = llm
                logger.debug(f"Added LLM to pool: {pool_key}")
            return llm
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

    # =========================================================
    # Pool Management
    # =========================================================

    @classmethod
    def enable_pool(cls, enabled: bool = True) -> None:
        """启用或禁用连接池"""
        cls._pool_enabled = enabled
        logger.info(f"Provider pool {'enabled' if enabled else 'disabled'}")

    @classmethod
    def clear_pool(cls, provider_type: str = "all") -> Dict[str, int]:
        """
        清空连接池

        Args:
            provider_type: "llm", "embedding", "reranker", 或 "all"

        Returns:
            各类型池清空的数量
        """
        counts = {}

        if provider_type in ("all", "llm"):
            count = len(cls._llm_pool)
            cls._llm_pool.clear()
            counts["llm"] = count
            logger.info(f"Cleared {count} LLM instances from pool")

        if provider_type in ("all", "embedding"):
            count = len(cls._embedding_pool)
            cls._embedding_pool.clear()
            counts["embedding"] = count
            logger.info(f"Cleared {count} Embedding instances from pool")

        if provider_type in ("all", "reranker"):
            count = len(cls._reranker_pool)
            cls._reranker_pool.clear()
            counts["reranker"] = count
            logger.info(f"Cleared {count} Reranker instances from pool")

        return counts

    @classmethod
    def get_pool_stats(cls) -> Dict[str, Any]:
        """获取连接池统计信息"""
        return {
            "enabled": cls._pool_enabled,
            "llm_count": len(cls._llm_pool),
            "embedding_count": len(cls._embedding_pool),
            "reranker_count": len(cls._reranker_pool),
            "total_instances": len(cls._llm_pool) + len(cls._embedding_pool) + len(cls._reranker_pool),
        }