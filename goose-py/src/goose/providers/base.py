# providers/base.py
from abc import ABC, abstractmethod
import logging
from typing import List, Tuple, Any, AsyncGenerator, Optional,Dict,Protocol
from pydantic import BaseModel
from ..conversation import Message
from .model_config import ModelConfig
from .types import Document

logger = logging.getLogger(__name__)

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

# class Provider(ABC):
#     """
#     对应 Rust: pub trait Provider
#     """
#     name: str = "base"

#     def __init__(self, model_config: Dict[str, Any]):
#         """
#         :param model_config: 包含 api_key, base_url, model_name 等配置的字典
#         """
#         self.config = model_config

#     @abstractmethod
#     def get_model_config(self) -> ModelConfig:
#         pass

#     @abstractmethod
#     async def agenerate(
#         self, 
#         system: str, 
#         messages: List[Message], 
#         tools: List[Any] = []
#     ) -> Tuple[Message, ProviderUsage]:
#         """非流式调用"""
#         logger.warning("This provider does not support non-streaming completions")
#         pass

#     @abstractmethod
#     async def astream(
#         self,
#         system: str,
#         messages: List[Message],
#         tools: List[Any] = []
#     ) -> AsyncGenerator[Tuple[Optional[Message], Optional[ProviderUsage]], None]:
#         """
#         流式调用 (Streaming)
#         对应 Rust: async fn stream(...) -> Result<MessageStream, ...>
        
#         Yields:
#             (Message片段, Usage信息)
#             注意：在流式传输中，Message 可能是增量的文本，Usage 可能只在最后一次返回。
#         """
#         pass


#     async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
#         """
#         生成文本向量
#         """
#         logger.warning("This provider does not support embeddings")


#     async def rerank(
#         self, 
#         query: str, 
#         documents: List[str], 
#         top_n: Optional[int] = None
#     ) -> List[RerankResult]:
#         """
#         重排序
#         """
#         logger.warning("This provider does not support reranking")



"""
Base Interfaces (SPI) for AI Services.
"""

class BaseLLM(ABC):
    """
    [Core SPI] 标准 LLM 客户端接口 (Abstract Base Class)
    """

    @abstractmethod
    async def agenerate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[Message, ProviderUsage]:
        """
        [必须实现] 异步生成完整回复
        """
        ...

    @abstractmethod
    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> AsyncGenerator[Tuple[Message, Optional[ProviderUsage]], None]:
        """
        [必须实现] 异步流式生成
        Yields: (PartialMessage, Usage)
        """
        ...


class BaseEmbedding(ABC):
    """
    [Core SPI] 标准 Embedding 客户端接口
    """

    @abstractmethod
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """[必须实现] 异步批量 Embed"""
        ...

    @abstractmethod
    async def aembed_query(self, text: str) -> List[float]:
        """[必须实现] 异步单条 Embed"""
        ...

    # --- 同步方法 (可选，提供默认实现以便向后兼容) ---
    # 如果你的系统是全异步的 (FastAPI/MicroAgent)，其实可以去掉同步接口，保持纯净。
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """同步 Embed (Optional)"""
        raise NotImplementedError("Sync embedding not implemented")

    def embed_query(self, text: str) -> List[float]:
        """同步 Embed (Optional)"""
        raise NotImplementedError("Sync embedding not implemented")

class Provider(BaseLLM,BaseEmbedding):
    """
    [Core SPI] 标准 Provider 接口
    """
    def __init__(self, model_config: ModelConfig):
        self.config = model_config

    @abstractmethod
    def get_model_config(self) -> ModelConfig:
        pass

    @abstractmethod
    async def agenerate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[Message, ProviderUsage]:
        """
        [必须实现] 异步生成完整回复
        """
        ...

    @abstractmethod
    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> AsyncGenerator[Tuple[Message, Optional[ProviderUsage]], None]:
        """
        [必须实现] 异步流式生成
        Yields: (PartialMessage, Usage)
        """
        ...


    @abstractmethod
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """[必须实现] 异步批量 Embed"""
        ...

    @abstractmethod
    async def aembed_query(self, text: str) -> List[float]:
        """[必须实现] 异步单条 Embed"""
        ...
        
    
class BaseReranker(ABC):
    """
    [Core SPI] 重排序服务接口
    """

    @abstractmethod
    async def arerank(
        self, 
        query: str, 
        documents: List[Document], 
        top_k: int = 5
    ) -> List[Document]:
        """
        [必须实现] 异步重排序
        """
        ...

    # --- 同步方法 (可选) ---
    def rerank(
        self, 
        query: str, 
        documents: List[Document], 
        top_k: int = 5
    ) -> List[Document]:
        """同步重排序 (Optional)"""
        raise NotImplementedError("Sync rerank not implemented")