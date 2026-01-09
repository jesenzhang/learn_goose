# ai_services.py
from abc import ABC, abstractmethod
from typing import List,Any,Dict,TypeVar,Optional,Callable

# 定义泛型 T，代表 docs 可以是任何类型的列表 (str, dict, object...)
T = TypeVar("T")

class BaseAIService(ABC):
    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        pass
    
    
    async def rerank(self, query: str, docs: List[T], key_func: Optional[Callable[[T], str]] = None, top: int = -1, threshold: float =0) -> List[T]:
        """
        对文档列表进行重排序。
        
        Args:
            query: 查询语句
            docs: 待排序的文档列表（可以是字符串列表，也可以是对象列表）
            key: 一个函数，用于从 docs 的元素中提取用于计算相似度的文本。
                 如果 docs 是字符串列表，则 key 为 None。
        """
        raise NotImplementedError

from embedding_client import TEIEmbedding,TEIEmbeddingConfig
from rerank_client import Reranker, RerankerConfig

class OpenAI_Service(BaseAIService):
    def __init__(self):

        self.embedding_client = TEIEmbedding(TEIEmbeddingConfig(base_url="http://192.168.10.137:8002"))
        self.rerank_client = Reranker(RerankerConfig(base_url="http://192.168.10.137:8079/rerank",type="openai"))
        
    async def embed_query(self, text: str) -> List[float]:
        # 模拟调用
        try:
            embeddings = await self.embedding_client.aembed_query(text)
        except Exception as e:
            print(f"Error occurred: {e}")
            return None
        return embeddings

    async def rerank(self, query: str, docs: List[T], key_func: Optional[Callable[[T], str]] = None, top: int = -1, threshold: float =0) -> List[T]:
        if not docs:
            return []

        # 1. 提取用于计算分数的文本列表
        if key_func:
            # 如果提供了 key 函数，用它提取文本
            texts_to_score = [key_func(doc) for doc in docs]
        else:
            # 如果没提供，假设 docs 本身就是字符串列表
            texts_to_score = docs
        # 2. 调用模型获取分数
        # 构造 [[query, text1], [query, text2], ...]
        pairs = [[query, text] for text in texts_to_score]
        try:
            scores = await self.rerank_client(pairs)
        except Exception as e:
            print(f"Rerank failed: {e}")
            return docs # 失败降级：返回原列表
        if not scores or len(scores) != len(docs):
            return docs
        combined = list(zip(docs, scores))
        combined.sort(key=lambda x: x[1], reverse=True)
        sorted_docs = [doc for doc, score in combined if score > threshold] 
        if top > 0:
            sorted_docs = sorted_docs[:top]
        return sorted_docs

    def ranker_filter(self,documents: List[Any], scores: List[float],re_sort:bool = True, threshold: float =0) -> List[Any]:
        """
        根据得分对文档列表进行重排序，并只保留得分大于阈值的文档。

        Args:
            documents (List[str]): 文档列表。
            scores (List[float]): 每个文档对应的得分列表。
            threshold (float): 得分阈值。
        Returns:
            List[str]: 按照得分从高到低排序且得分大于阈值的文档列表。
        """
        if scores==None:
            return documents
        if len(documents) != len(scores):
            raise ValueError("文档列表和得分列表的长度必须相同。")
        # 将文档和得分组合成一个元组列表
        sorted_pairs = list(zip(documents, scores))
        # 根据得分从高到低排序
        if re_sort:
            sorted_pairs = sorted(sorted_pairs, key=lambda x: x[1], reverse=True)
        # 提取排序后的文档列表，只保留得分大于阈值的文档 筛选和赋值同时完成。
        filtered_pairs =[(doc, score) for doc, score in sorted_pairs if score > threshold]
        sorted_documents, sorted_scores = zip(*filtered_pairs) if filtered_pairs else ([], [])
        return sorted_documents,sorted_scores


async def main():
    ai_service = OpenAI_Service()
    query = "如何使用 Python 创建一个简单的 Web 服务器？"
    docs = ["如何使用 Python 创建一个简单的 Web 服务器？", "如何使用 Python 创建一个简单的 Web 服务器？", "如何使用 Python 创建一个简单的 Web 服务器？"]
    embeddings = await ai_service.embed_query(query)
    print(embeddings)
    sorted_docs = await ai_service.rerank(query, docs)
    print(sorted_docs)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
