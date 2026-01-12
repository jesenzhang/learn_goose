# providers/base.py
from abc import ABC, abstractmethod
import logging
from typing import List, Tuple, Any, AsyncGenerator, Optional,Dict,Protocol,Callable,TypeVar
from pydantic import BaseModel
from ..conversation import Message
from .model_config import ModelConfig
from .types import Document

logger = logging.getLogger(__name__)

# 定义泛型 T
T = TypeVar("T")

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
    
    
    # =========================================================================
    #  ✨ 新增：通用便捷方法 (Template Method)
    # =========================================================================
    async def rank_objects(
        self, 
        query: str, 
        items: List[T], 
        key_func: Optional[Callable[[T], str]] = None, 
        top_k: int = 5, 
        threshold: float = 0.0
    ) -> List[T]:
        """
        [便捷方法] 对任意对象列表进行重排序。
        
        Args:
            query: 查询语句
            items: 待排序的对象列表 (可以是 str, dict, pydantic model 等)
            key_func: 从对象提取文本的函数。如果 items 是 str 列表，可为 None。
            top_k: 返回前 K 个
            threshold: 分数阈值，低于此分数的将被过滤
            
        Returns:
            List[T]: 排序并过滤后的原始对象列表
        """
        if not items:
            return []

        # 1. 转换为 Document 对象，并通过 metadata 绑定原始索引
        docs_map: List[Document] = []
        for idx, item in enumerate(items):
            # 提取文本
            if key_func:
                text_content = key_func(item)
            elif isinstance(item, str):
                text_content = item
            elif hasattr(item, "page_content"): # 兼容 LangChain Document
                text_content = item.page_content
            else:
                text_content = str(item) # 兜底

            # 构造 Document，保留原始索引以便还原
            docs_map.append(
                Document(
                    page_content=text_content, 
                    metadata={"_original_index": idx}
                )
            )

        # 2. 调用底层 Provider (请求全量排序，以便后续做阈值过滤)
        # 注意：这里我们请求 len(items) 而不是 top_k，因为如果先截断再过滤，可能会导致结果少于 top_k
        # 实际生产中，为了性能，也可以传 max(top_k * 2, 20) 之类的缓冲值
        ranked_docs = await self.arerank(query, docs_map, top_k=len(items))

        # 3. 还原对象并应用阈值
        results: List[T] = []
        for doc in ranked_docs:
            # 过滤阈值 (假设 arerank 返回的是降序，遇到低于阈值的可以 continue 或 break)
            # 考虑到有些模型分数分布不同，这里用 continue 更稳妥
            if (doc.score or 0.0) < threshold:
                continue
            
            # 还原原始对象
            original_idx = doc.metadata.get("_original_index")
            if original_idx is not None and 0 <= original_idx < len(items):
                # 可选：如果你想把分数注入回原始对象（如果是 dict 或对象），可以在这里做
                # 但为了纯粹性，这里只返回原对象
                results.append(items[original_idx])
            
            # 达到数量限制则停止
            if len(results) >= top_k:
                break
                
        return results