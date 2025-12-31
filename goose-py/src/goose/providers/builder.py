from typing import Any
from goose.resources.builder import ResourceBuilder
from goose.resources.types import ResourceMetadata
from goose.providers.factory import ProviderFactory

class LLMBuilder(ResourceBuilder):
    async def build(self, meta: ResourceMetadata) -> Any:
        # 这里处理 provider 映射逻辑
        provider_type = meta.provider # e.g. "openai"
        config = meta.config
        
        if provider_type == "openai":
            return ProviderFactory.create(provider_type,config)
        else:
            raise ValueError(f"Unknown LLM provider: {provider_type}")