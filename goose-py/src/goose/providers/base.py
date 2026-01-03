# providers/base.py
from abc import ABC, abstractmethod
from typing import List, Tuple, Any, AsyncGenerator, Optional,Dict
from pydantic import BaseModel
from goose.conversation import Message
from .model_config import ModelConfig
from .types import RerankResult,Document

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


    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        生成文本向量
        """
        raise NotImplementedError("This provider does not support embeddings")


    async def rerank(
        self, 
        query: str, 
        documents: List[str], 
        top_n: Optional[int] = None
    ) -> List[RerankResult]:
        """
        重排序
        """
        raise NotImplementedError("This provider does not support reranking")

class LLMClient(Protocol):
    """
    [Core SPI] 标准 LLM 客户端接口
    组件只调用这些方法，不关心底层是 LangChain 还是 OpenAI 原生 SDK
    """

    @abstractmethod
    async def ainvoke(
        self,
        messages: List["ChatMessage"],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[Message, ProviderUsage]:
        """异步生成完整回复"""
        pass

    @abstractmethod
    async def astream(
        self,
        messages: List["ChatMessage"],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> AsyncGenerator[Tuple[Optional[Message], Optional[ProviderUsage]], None]:
        """异步流式生成"""
        pass


class EmbeddingClient(Protocol):
    """
    [Core SPI] 标准 Embedding 客户端接口
    """

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Asynchronous Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """

    async def aembed_query(self, text: str) -> list[float]:
        """Asynchronous Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """


class RerankClient(Protocol):
    """
    OpenCoze 标准重排序模型接口
    """

    @abstractmethod
    def rerank(
        self, documents: List[Document], query: str, top_k: int = None
    ) -> List[Document]:
        """
        对文本列表进行重排序
        """
        pass

    # 也可以支持 LangChain Document 对象的重载
    async def arerank(
        self, documents: List[Document], query: str, top_k: int = None
    ) -> List[Document]:
        """异步重排序"""
        # 默认同步回退，具体实现可覆盖
        return self.rerank(query, documents, top_k)
