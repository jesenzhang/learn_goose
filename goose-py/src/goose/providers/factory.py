import logging
from typing import Dict, Type, Any, Optional
from .base import Provider

logger = logging.getLogger("goose.providers.factory")

class ProviderFactory:
    """
    Provider 工厂类。
    支持动态注册和实例化。
    """
    # 注册表：存储 "provider_name" -> ProviderClass
    _registry: Dict[str, Type[Provider]] = {}

    @classmethod
    def register(cls, name: str):
        """
        [装饰器] 用于将 Provider 类注册到工厂。
        @ProviderFactory.register("openai")
        class OpenAIProvider(Provider): ...
        """
        def decorator(provider_cls: Type[Provider]):
            if name in cls._registry:
                logger.warning(f"Provider '{name}' already registered. Overwriting.")
            
            cls._registry[name] = provider_cls
            # 同时把 name 注入到类属性中，方便反查
            provider_cls.name = name
            return provider_cls
        return decorator

    @classmethod
    def create(cls, provider_name: str, model_config: Dict[str, Any]) -> Provider:
        """
        工厂方法：根据名称创建实例。
        """
        if provider_name not in cls._registry:
            valid_keys = list(cls._registry.keys())
            raise ValueError(f"Unknown provider '{provider_name}'. Available: {valid_keys}")

        provider_cls = cls._registry[provider_name]
        
        try:
            # 实例化
            return provider_cls(model_config)
        except Exception as e:
            logger.error(f"Failed to instantiate provider '{provider_name}': {e}")
            raise e

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._registry.keys())