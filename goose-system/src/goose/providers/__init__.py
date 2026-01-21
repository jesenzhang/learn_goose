"""
Providers Module

Provider implementations for LLM, Embedding, and Reranker services.
Reference: goose-rs Provider system and assistant providers.
"""

from .base import (
    Usage,
    ProviderUsage,
    ModelConfig,
    InferenceConfig,
    BaseLLM,
    BaseEmbedding,
    BaseReranker,
    Provider,
    Document,
    ToolDefinition,
    ProviderMetadata,
)
from .factory import ProviderFactory
from .errors import (
    ProviderError,
    AuthenticationError,
    RequestFailedError,
    ContextLengthExceededError,
    UsageError,
    ExecutionError,
    NotImplementedError,
)
from .message import (
    Role,
    TextContent,
    ToolRequest,
    ToolResponse,
    Message,
)

try:
    from .openai import OpenAIProvider
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAIProvider = None

__all__ = [
    # Base interfaces
    "Usage",
    "ProviderUsage",
    "ModelConfig",
    "InferenceConfig",
    "BaseLLM",
    "BaseEmbedding",
    "BaseReranker",
    "Provider",
    "Document",
    "ToolDefinition",
    "ProviderMetadata",
    # Factory
    "ProviderFactory",
    # Errors
    "ProviderError",
    "AuthenticationError",
    "RequestFailedError",
    "ContextLengthExceededError",
    "UsageError",
    "ExecutionError",
    "NotImplementedError",
    # Message types
    "Role",
    "TextContent",
    "ToolRequest",
    "ToolResponse",
    "Message",
    # Providers
    "OpenAIProvider",
    "OPENAI_AVAILABLE",
]


def create_llm(provider_name: str, config: dict) -> BaseLLM:
    """Create LLM provider instance."""
    return ProviderFactory.create_llm(provider_name, config)


def create_embedding(provider_name: str, config: dict) -> BaseEmbedding:
    """Create Embedding provider instance."""
    return ProviderFactory.create_embedding(provider_name, config)


def list_providers() -> dict:
    """List all available providers."""
    return {
        "llm": ProviderFactory.list_llm_providers(),
        "embedding": ProviderFactory.list_embedding_providers(),
        "reranker": ProviderFactory.list_reranker_providers(),
    }


class ProviderWrapper:
    """Provider 包装器"""
    
    def __init__(self, provider: Provider):
        self.provider = provider
    
    @property
    def model_config(self):
        """获取模型配置"""
        return self.provider.get_model_config()
    
    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None
    ):
        """完成调用"""
        from .message import Role as MsgRole
        from .base import Usage
        
        provider_messages = []
        for msg in messages:
            role_str = msg.get("role", "user")
            try:
                role = MsgRole(role_str.upper())
            except ValueError:
                role = MsgRole.USER
            
            content = msg.get("content", "")
            if isinstance(content, str):
                provider_messages.append(Message(role=role, content=[TextContent(text=content)]))
            else:
                provider_messages.append(Message(role=role, content=[]))
        
        result, usage = await self.provider.agenerate(
            messages=provider_messages,
            tools=tools
        )
        
        content = result.text or ""
        
        tool_calls = []
        for c in result.content:
            if isinstance(c, ToolRequest):
                tool_calls.append({
                    "id": c.id,
                    "name": c.name,
                    "arguments": c.arguments or {}
                })
        
        usage_dict = {}
        if usage:
            usage_dict = {
                "input_tokens": usage.usage.input_tokens if hasattr(usage, 'usage') else 0,
                "output_tokens": usage.usage.output_tokens if hasattr(usage, 'usage') else 0,
                "total_tokens": usage.usage.total_tokens if hasattr(usage, 'usage') else 0
            }
        
        response = Message.assistant(content)
        
        return response, usage_dict
    
    async def stream(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None
    ):
        """流式调用"""
        from .message import Role as MsgRole
        
        provider_messages = []
        for msg in messages:
            role_str = msg.get("role", "user")
            try:
                role = MsgRole(role_str.upper())
            except ValueError:
                role = MsgRole.USER
            
            content = msg.get("content", "")
            if isinstance(content, str):
                provider_messages.append(Message(role=role, content=[TextContent(text=content)]))
            else:
                provider_messages.append(Message(role=role, content=[]))
        
        async for chunk in self.provider.astream(
            messages=provider_messages,
            tools=tools
        ):
            message, usage = chunk
            content = message.text or ""
            usage_dict = {}
            if usage:
                usage_dict = {
                    "input_tokens": usage.usage.input_tokens if hasattr(usage, 'usage') else 0,
                    "output_tokens": usage.usage.output_tokens if hasattr(usage, 'usage') else 0,
                    "total_tokens": usage.usage.total_tokens if hasattr(usage, 'usage') else 0
                }
            response = Message.assistant(content)
            yield response, usage_dict
    
    def _simulate_complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None
    ):
        """模拟完成（回退方案）"""
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        
        response = Message.assistant(f"[Simulated] {last_user_msg}")
        return response, {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}


def create_provider(
    provider_type: str,
    config: dict
) -> ProviderWrapper | None:
    """
    创建 Provider
    
    Args:
        provider_type: Provider 类型 (openai, etc.)
        config: 配置字典
        
    Returns:
        ProviderWrapper 实例
    """
    try:
        provider = ProviderFactory.create_llm(provider_type, config)
        return ProviderWrapper(provider)
    except ValueError as e:
        print(f"Failed to create provider: {e}")
        return None


def list_available_providers() -> list[str]:
    """列出可用的 Providers"""
    return ProviderFactory.list_llm_providers()
