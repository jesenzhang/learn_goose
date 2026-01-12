"""
Embedding Providers Implementation.
Supports: OpenAI, TEI (Text Embeddings Inference), and Custom HTTP backends.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union

import httpx
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type

from .base import BaseEmbedding
from .factory import ProviderFactory

logger = logging.getLogger(__name__)

# =========================================================================
# Shared Base: HTTP & Batching Logic
# =========================================================================

class BaseHttpEmbedding(BaseEmbedding):
    """
    通用 HTTP Embedding 基类。
    负责：连接池管理、并发限制、分批处理、URL 自动修复。
    """
    def __init__(
        self, 
        base_url: str, 
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        concurrency: int = 10,
        batch_size: int = 32
    ):
        # [FIX] URL 自我修复
        self.base_url = self._normalize_base_url(base_url)
        self.batch_size = batch_size
        
        # 共享连接池
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {}
        )
        # 信号量控制并发请求数
        self._sem = asyncio.Semaphore(concurrency)

    def _normalize_base_url(self, url: str) -> str:
        """补全协议头，去除尾部斜杠"""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        return url.rstrip('/')

    def _resolve_endpoint(self, suffix: str) -> str:
        """
        智能拼接 Endpoint。
        如果 base_url 已经包含了 suffix，则不再重复添加。
        """
        if not suffix.startswith('/'):
            suffix = f"/{suffix}"
            
        # 如果 base_url 结尾已经是这个 suffix，直接返回
        if self.base_url.endswith(suffix):
            return self.base_url
            
        return f"{self.base_url}{suffix}"

    async def close(self):
        await self.client.aclose()

    async def _batch_process(self, texts: List[str], process_func) -> List[List[float]]:
        """
        通用的分批 + 并发处理逻辑
        """
        if not texts:
            return []

        tasks = []
        total = len(texts)
        
        # 1. 创建批次任务
        for i in range(0, total, self.batch_size):
            batch_texts = texts[i : i + self.batch_size]
            tasks.append(process_func(batch_texts))

        # 2. 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 3. 结果合并
        final_embeddings = []
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"❌ Embedding Batch {idx} failed: {res}")
                # 严重错误，抛出以便上层感知配置问题
                raise res 
            else:
                final_embeddings.extend(res)
                
        return final_embeddings

    # --- 接口实现 ---

    async def aembed_query(self, text: str) -> List[float]:
        res = await self.aembed_documents([text])
        return res[0] if res else []

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


# =========================================================================
# 1. TEI (Text Embeddings Inference) Provider
# =========================================================================

@ProviderFactory.register_embedding("tei")
class TEIEmbedding(BaseHttpEmbedding):
    """
    Standard HuggingFace TEI Client.
    API: POST /embed
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            base_url=config.get("base_url", "http://localhost:8080"),
            api_key=config.get("api_key"),
            timeout=config.get("timeout", 30),
            concurrency=config.get("concurrency", 10),
            batch_size=config.get("batch_size", 32)
        )
        self.truncate = config.get("truncate", True)
        self.normalize = config.get("normalize", True)
        
        # [FIX] 支持自定义 route，默认为 /embed
        route = config.get("route", "/embed")
        self.endpoint_url = self._resolve_endpoint(route)
        logger.info(f"TEI Embedding initialized. Target URL: {self.endpoint_url}")

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        
        async def _process_batch(batch: List[str]) -> List[List[float]]:
            payload = {
                "inputs": batch,
                "truncate": self.truncate,
                "normalize": self.normalize
            }
            async with self._sem:
                try:
                    # [DEBUG]
                    # logger.debug(f"🚀 Embedding batch of {len(batch)} items to {self.endpoint_url}")
                    resp = await self.client.post(self.endpoint_url, json=payload)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e:
                    logger.error(f"TEI Request failed: {e}")
                    raise e

        return await self._batch_process(texts, _process_batch)


# =========================================================================
# 2. Custom JSON Provider (原 TextEmbedding 类)
# =========================================================================

@ProviderFactory.register_embedding("custom_json")
class CustomJSONEmbedding(BaseHttpEmbedding):
    """
    适配特殊接口格式:
    POST / (root)
    Payload: {"data": {"id": "...", "text": "..."}}
    Response: {"data": {"fields": {"TextVectors": [...]}}}
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            base_url=config.get("base_url", "http://localhost:8080"),
            api_key=config.get("api_key"),
            timeout=config.get("timeout", 60),
            concurrency=config.get("concurrency", 20),
            batch_size=config.get("batch_size", 32) 
        )
        
        # [FIX] 默认为根路径 "/"，但也支持配置 route
        route = config.get("route", "/")
        self.endpoint_url = self._resolve_endpoint(route)
        logger.info(f"Custom JSON Embedding initialized. Target URL: {self.endpoint_url}")

    @retry(
        wait=wait_random_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
    )
    async def _embed_single(self, text: str, idx: int) -> List[float]:
        """发送单条请求"""
        payload = {
            "data": {
                "id": str(idx),
                "text": text
            }
        }
        async with self._sem:
            # 使用计算好的 endpoint_url
            resp = await self.client.post(self.endpoint_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            vec = data.get("data", {}).get("fields", {}).get("TextVectors", [])
            if not vec:
                logger.warning(f"Empty vector for index {idx}")
            return vec

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        async def _process_batch_concurrently(batch: List[str]) -> List[List[float]]:
            # 在一个 batch 内再进行并发
            tasks = [self._embed_single(text, i) for i, text in enumerate(batch)]
            return await asyncio.gather(*tasks)

        return await self._batch_process(texts, _process_batch_concurrently)


# =========================================================================
# 3. OpenAI Embedding (Standard)
# =========================================================================

from openai import AsyncOpenAI

@ProviderFactory.register_embedding("openai_embedding")
class OpenAIEmbeddingProvider(BaseEmbedding):
    """
    Standard OpenAI Embedding (or Compatible API like vLLM).
    """
    def __init__(self, config: Dict[str, Any]):
        # [FIX] 即使是 OpenAI SDK，也最好清洗一下 base_url，防止用户漏写 http://
        base_url = config.get("base_url")
        if base_url:
            base_url = base_url.strip()
            if not base_url.startswith(("http://", "https://")):
                base_url = f"http://{base_url}"
            # OpenAI SDK 通常会自动处理 /v1 等，但我们可以根据情况 rstrip
            # 这里保守一点，只补协议头
        
        self.client = AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=base_url
        )
        self.model = config.get("model", "text-embedding-3-small")
        logger.info(f"OpenAI Embedding initialized. Model: {self.model}, Base URL: {base_url}")

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        # 简单的换行符清洗
        texts = [t.replace("\n", " ") for t in texts]
        
        try:
            resp = await self.client.embeddings.create(input=texts, model=self.model)
            # 确保按 index 排序返回
            data = sorted(resp.data, key=lambda x: x.index)
            return [d.embedding for d in data]
        except Exception as e:
            logger.error(f"OpenAI Embedding failed: {e}")
            raise e

    async def aembed_query(self, text: str) -> List[float]:
        res = await self.aembed_documents([text])
        return res[0]