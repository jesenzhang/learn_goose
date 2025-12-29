# providers/base.py
from abc import ABC, abstractmethod
from typing import List, Tuple, Any, AsyncGenerator, Optional,Dict
from pydantic import BaseModel
from goose.conversation import Message
from goose.model import ModelConfig

class Usage(BaseModel):
    """对应 Rust: pub struct Usage"""
    input_tokens: Optional[int] = 0
    output_tokens: Optional[int] = 0
    total_tokens: Optional[int] = 0

    def __add__(self, other: 'Usage') -> 'Usage':
        """复现 Rust 中的 Add trait，用于 Token 累加"""
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            input_tokens=(self.input_tokens or 0) + (other.input_tokens or 0),
            output_tokens=(self.output_tokens or 0) + (other.output_tokens or 0),
            total_tokens=(self.total_tokens or 0) + (other.total_tokens or 0),
        )

class ProviderUsage(BaseModel):
    """对应 Rust: pub struct ProviderUsage"""
    model: str
    usage: Usage

class Provider(ABC):
    """
    对应 Rust: pub trait Provider
    """
    name: str = "base"

    def __init__(self, model_config: Dict[str, Any]):
        """
        :param model_config: 包含 api_key, base_url, model_name 等配置的字典
        """
        self.config = model_config

    @abstractmethod
    def get_model_config(self) -> ModelConfig:
        pass

    @abstractmethod
    async def complete(
        self, 
        system: str, 
        messages: List[Message], 
        tools: List[Any] = []
    ) -> Tuple[Message, ProviderUsage]:
        """非流式调用"""
        pass

    @abstractmethod
    async def stream(
        self,
        system: str,
        messages: List[Message],
        tools: List[Any] = []
    ) -> AsyncGenerator[Tuple[Optional[Message], Optional[ProviderUsage]], None]:
        """
        流式调用 (Streaming)
        对应 Rust: async fn stream(...) -> Result<MessageStream, ...>
        
        Yields:
            (Message片段, Usage信息)
            注意：在流式传输中，Message 可能是增量的文本，Usage 可能只在最后一次返回。
        """
        pass