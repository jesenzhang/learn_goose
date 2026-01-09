"""
Reranker Providers Implementation.
Supports: HuggingFace Inference, TEI, and OpenAI-compatible (LLM-based) Rerankers.
"""

import asyncio
import logging
import math
from typing import List, Dict, Any, Optional, Tuple

import httpx
from pydantic import BaseModel

from .base import BaseReranker
from .types import Document
from .factory import ProviderFactory

logger = logging.getLogger(__name__)

# =========================================================================
# Shared Mixin: Batch Processing & HTTP Client
# =========================================================================

class BaseHttpReranker(BaseReranker):
    """
    通用 HTTP Reranker 基类。
    提供：连接池管理、并发控制、URL 自动修复、分批处理模板。
    """
    def __init__(
        self, 
        base_url: str, 
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        concurrency: int = 5
    ):
        # [FIX] URL 自我修复逻辑
        self.base_url = self._normalize_base_url(base_url)
        self.api_key = api_key
        
        # 共享连接池
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {}
        )
        # 并发信号量
        self._sem = asyncio.Semaphore(concurrency)

    def _normalize_base_url(self, url: str) -> str:
        """清洗 Base URL，补全协议头"""
        url = url.strip()
        # 1. 补全协议头
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        # 2. 去除尾部斜杠，方便后续拼接
        return url.rstrip('/')

    def _resolve_endpoint(self, suffix: str) -> str:
        """
        智能拼接 Endpoint。
        如果 base_url 已经包含了 suffix (如 /rerank)，则不再重复添加。
        """
        # 确保 suffix 以 / 开头
        if not suffix.startswith('/'):
            suffix = f"/{suffix}"
            
        # 如果配置的 base_url 已经以该后缀结尾，直接使用 base_url
        # 例如: http://host:8000/rerank + /rerank -> http://host:8000/rerank
        if self.base_url.endswith(suffix):
            return self.base_url
            
        # 否则拼接: http://host:8000 + /rerank -> http://host:8000/rerank
        return f"{self.base_url}{suffix}"

    async def close(self):
        await self.client.aclose()

    async def _batch_process(
        self, 
        query: str, 
        documents: List[Document], 
        batch_size: int, 
        process_func
    ) -> List[Document]:
        """
        通用的分批处理逻辑
        """
        if not documents:
            return []

        total = len(documents)
        tasks = []
        
        # 1. 创建批次任务
        for i in range(0, total, batch_size):
            batch_docs = documents[i : i + batch_size]
            tasks.append(process_func(query, batch_docs, start_index=i))

        # 2. 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 3. 结果合并与处理
        all_results = []
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"❌ Batch {idx} failed: {res}")
                # 降级：如果某一批次失败，保留原文档但分数为 -1
                start_idx = idx * batch_size
                failed_batch = documents[start_idx : start_idx + batch_size]
                for doc in failed_batch:
                    # [FIX] 确保 Document 定义中有 score 字段，否则这里会报错
                    if hasattr(doc, "score"):
                        doc.score = -1.0 
                    all_results.append(doc)
            else:
                all_results.extend(res)

        # 4. 再次按分数排序
        all_results.sort(key=lambda x: getattr(x, "score", -1.0) or -1.0, reverse=True)
        
        return all_results


# =========================================================================
# 1. HuggingFace Inference / TEI Reranker
# =========================================================================

@ProviderFactory.register_reranker("tei")
@ProviderFactory.register_reranker("hf_inference")
class TEIReranker(BaseHttpReranker):
    """
    Text Embeddings Inference (TEI) & HuggingFace Inference API Reranker.
    Standard Endpoint: POST /rerank
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            base_url=config.get("base_url", "http://localhost:8080"),
            api_key=config.get("api_key"),
            concurrency=config.get("concurrency", 10)
        )
        self.top_k = config.get("top_k", 5)
        self.batch_size = config.get("batch_size", 32)
        
        route = config.get("route", "/rerank")
        # [FIX] 预先计算好完整的 URL
        self.endpoint_url = self._resolve_endpoint(route)
        logger.info(f"TEI Reranker initialized. Target URL: {self.endpoint_url}")

    async def arerank(
        self, 
        query: str, 
        documents: List[Document], 
        top_k: int = 5
    ) -> List[Document]:
        
        async def _process_batch(q: str, batch: List[Document], start_index: int) -> List[Document]:
            texts = [d.page_content for d in batch]
            payload = {
                "query": q,
                "texts": texts,
                "truncate": True 
            }
            
            async with self._sem:
                try:
                    # [DEBUG] 详细日志
                    logger.debug(f"🚀 Requesting {self.endpoint_url} (Batch len: {len(texts)})")
                    
                    resp = await self.client.post(self.endpoint_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Request failed to {self.endpoint_url}. Error: {e}")
                    raise e
                
            processed_batch = []
            for item in data:
                idx = item["index"]
                if 0 <= idx < len(batch):
                    doc = batch[idx].model_copy()
                    doc.score = item["score"]
                    processed_batch.append(doc)
            
            return processed_batch

        results = await self._batch_process(query, documents, self.batch_size, _process_batch)
        return results[:top_k]


# =========================================================================
# 2. OpenAI-Compatible Reranker (Custom/BGE Implementation)
# =========================================================================

@ProviderFactory.register_reranker("openai")
class OpenAIReranker(BaseHttpReranker):
    """
    Local LLM/BGE Service mimicking OpenAI Protocol.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            base_url=config.get("base_url", "http://127.0.0.1:8003"),
            api_key=config.get("api_key"),
            concurrency=config.get("concurrency", 5)
        )
        self.top_k = config.get("top_k", 5)
        self.batch_size = config.get("batch_size", 16)
        
        route = config.get("route", "/rerank")
        self.endpoint_url = self._resolve_endpoint(route)
        logger.info(f"OpenAI Reranker initialized. Target URL: {self.endpoint_url}")

    async def arerank(
        self, 
        query: str, 
        documents: List[Document], 
        top_k: int = 5
    ) -> List[Document]:

        async def _process_batch(q: str, batch: List[Document], start_index: int) -> List[Document]:
            batch_texts = [d.page_content[:2000] for d in batch] 
            
            # Prompt Construction
            prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query...<|im_end|>\n<|im_start|>user\n'
            suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            instruction = "Given a web search query, retrieve relevant passages that answer the query"
            
            prompt_query = f"{prefix}<Instruct>: {instruction}\n<Query>: {q}\n"
            formatted_docs = [f"<Document>: {doc}{suffix}" for doc in batch_texts]
            
            payload = {
                "query": prompt_query,
                "documents": formatted_docs
            }
            
            async with self._sem:
                try:
                    logger.debug(f"🚀 Requesting {self.endpoint_url} (Batch len: {len(batch)})")
                    resp = await self.client.post(self.endpoint_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Request failed to {self.endpoint_url}. Error: {e}")
                    raise e
            
            results_data = data.get("results", [])
            processed_batch = []
            
            for item in results_data:
                idx = item.get("index")
                score = item.get("relevance_score", 0.0)
                
                if idx is not None and 0 <= idx < len(batch):
                    doc = batch[idx].model_copy()
                    doc.score = score
                    processed_batch.append(doc)
            
            return processed_batch

        results = await self._batch_process(query, documents, self.batch_size, _process_batch)
        return results[:top_k]


# =========================================================================
# 3. Cohere Reranker
# =========================================================================

@ProviderFactory.register_reranker("cohere")
class CohereReranker(BaseReranker):
    """
    Official Cohere Rerank Implementation.
    """
    def __init__(self, config: Dict[str, Any]):
        try:
            import cohere
            self.client = cohere.AsyncClient(config["api_key"]) 
        except ImportError:
            raise ImportError("Please install `cohere` to use CohereReranker.")
        
        self.model = config.get("model", "rerank-english-v3.0")
        self.top_k = config.get("top_k", 5)

    async def arerank(
        self, 
        query: str, 
        documents: List[Document], 
        top_k: int = 5
    ) -> List[Document]:
        if not documents: return []
        
        texts = [d.page_content for d in documents]
        
        try:
            response = await self.client.rerank(
                model=self.model,
                query=query,
                documents=texts,
                top_n=top_k or self.top_k
            )
            
            results = []
            for hit in response.results:
                # 兼容不同版本的 cohere SDK 响应结构
                idx = hit.index
                score = hit.relevance_score
                
                if 0 <= idx < len(documents):
                    doc = documents[idx].model_copy()
                    doc.score = score
                    results.append(doc)
                
            return results
            
        except Exception as e:
            logger.error(f"Cohere Rerank failed: {e}")
            # Fallback
            for doc in documents:
                doc.score = 0.0
            return documents[:top_k]