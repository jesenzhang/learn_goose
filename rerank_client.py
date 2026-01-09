from typing import Dict, List, Tuple,Any, Union, Optional, Any  
from pydantic import BaseModel
from loguru import logger
import aiohttp
import asyncio
from dataclasses import dataclass
from embedding_client import TEIEmbedding,TEIEmbeddingConfig

class hf_inference_reranker:
    def __init__(self,base_url) -> None:
        self.url = base_url

    async def is_api_available(self):
        """
        检查 API 链接是否可用
        """
        try:
            # 设置超时时间为 5 秒
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(self.url) as resp:
                    # 检查响应状态码是否为 200
                    return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.debug(f'is_api_available timeout: {self.url} ')
            return False

    async def predict(self,hits:List[Tuple[str, str]]|List[List[str]])-> Any:
        #检查 API 链接是否可用
        # if not await self.is_api_available():
        #     logger.error(f"The API {self.url} is not available. Skipping the request.")
        #     return None
        try : 
            if hits and len(hits)>0:
                query = hits[0][0]
                texts = [hit[1] for hit in hits]
                query_json = {
                    "query" : query,
                    "texts" : texts
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.url,json=query_json) as resp:
                        response = await resp.json()
                    response = sorted(response,key=lambda x : x["index"])
                    response = [i["score"] for i in response]
                return response
                    
        except Exception as e:
            logger.error(f"{type(self).__name__}  {e} \n")
        return None
        
    async def __call__(self, input:List[Tuple[str, str]]|List[List[str]]) -> Any:
        if not input:
            return []

        BATCH_SIZE = 32
        tasks = []

        # 分批创建异步任务
        for i in range(0, len(input), BATCH_SIZE):
            batch = input[i:i + BATCH_SIZE]
            task = self.predict(batch)  # 不 await，先收集 task
            tasks.append((i, task))     # 记录起始索引，用于排序

        # 并发执行所有批次
        results = []
        for start_idx, task in tasks:
            batch_scores = await task
            results.append((start_idx, batch_scores))

        # 按原始顺序排序并合并
        results.sort(key=lambda x: x[0])  # 按起始索引排序
        final_scores = []
        for _, batch_scores in results:
            final_scores.extend(batch_scores)

        return final_scores
    

class RerankerConfig(BaseModel):
    model_name : str = "reranker_v2.0"
    model_path: str = '/mnt/sdd1/pretrainedLM/pretrainedLM/bge-reranker-v2-m3'
    triton_url: str  = "localhost:5071"
    base_url : str = "http://localhost:8080/rerank"
    top_k : int = 5
    type: str =  'hf_inference'
    device : str = "cuda:6"


# 用于验证rerank接口返回的结果
class RerankScore(BaseModel):
    index: int = 0
    score: float = 0.0
    
class OpenaiReranker:
    def __init__(self,url="http://127.0.0.1:8003/rerank") -> None:
        self.url = url
        if self.url.endswith("/"):
            self.url = self.url.rstrip("/")
        if not self.url.endswith("/rerank"):
            self.url = self.url + "/rerank"
        
    
    async def __call__(self,query:str,texts:list[str],semaphore=1)->list[RerankScore]:
        ## 减少并发，避免超时报错
        ## 设定批次，每次最多32个
        
        RerankSemaphore = asyncio.Semaphore(semaphore)
        async def rerank(query:str,batch_texts:list[str])->list[RerankScore]:
            # 返回排序后的rerank结果，需要自行找回索引
            batch_texts = [i[:200] for i in batch_texts]
            prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
            suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            instruction = (
                    "Given a web search query, retrieve relevant passages that answer the query"
                ) 
            query = f"{prefix}<Instruct>: {instruction}\n<Query>: {query}\n"
            batch_texts = [f"<Document>: {doc}{suffix}" for doc in batch_texts]
            data = {
                "query":query,
                "documents":batch_texts
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, headers={"Content-Type": "application/json"}, json=data) as resp:
                    try:
                        result = await resp.json()
                        result = result["results"]
                        # 统一格式
                        result = [RerankScore(index=idx_score["index"],score=idx_score["relevance_score"]) for idx_score in result]
                        return result
                    except Exception as e:
                        # raise Exception(f"rerank失败，{e}")
                        result = [RerankScore(index=idx,score=0.0) for idx in range(len(batch_texts))]
                        return result
                    
        async def rerank_old(query:str,batch_texts:list[str])->list[RerankScore]:
            # 返回排序后的rerank结果，需要自行找回索引
            batch_texts = [i[:200] for i in batch_texts]
            data = {
                "query":query,
                "texts":batch_texts
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, headers={"Content-Type": "application/json"}, json=data) as resp:
                    try:
                        result = await resp.json()
                        # 统一格式
                        result = [RerankScore(index=idx_score["index"],score=idx_score["score"]) for idx_score in result]
                        return result
                    except Exception as e:
                        # raise Exception(f"rerank失败，{e}")
                        result = [RerankScore(index=idx,score=0.0) for idx in range(len(batch_texts))]
                        return result
        # 批次处理
        ## 接收全局并发限制
        async def rerank_batch(query:str,batch_texts:list[str],batch_start_idx:int)->list[RerankScore]:
            async with RerankSemaphore:
                results = await rerank(query,batch_texts)
                # 加上起始idx
                for item in results:
                    item.index += batch_start_idx
                return results
        tasks = []
        for i in range(0, len(texts), 16):
            end = min(i+16,len(texts))
            batch_texts = texts[i:end]
            tasks.append(
                asyncio.create_task(rerank_batch(query, batch_texts,i))
            )
        rrk_results = await asyncio.gather(*tasks)
        final_result = []
        for item in rrk_results:
            final_result.extend(item)
        # 排序
        final_result.sort(key=lambda x:x.index)
        return final_result


                
class Reranker():
    # triton 当前仅支持bs=1 
    def __init__(self, config: RerankerConfig|Dict ) -> None:
        if isinstance(config, dict):
            config = RerankerConfig.model_validate(config)
        elif isinstance(config, RerankerConfig):
            config = config
        else:
            config =  RerankerConfig()
        self.triton_url = config.triton_url
        self.base_url = config.base_url
        self.model_name  = config.model_name 
        self.top_k = config.top_k

        self.type = config.type
        if self.type =="hf_inference":
            self.model = hf_inference_reranker(config.base_url)
        elif self.type =="TEI":
            self.tei_client = TEIEmbedding(TEIEmbeddingConfig(base_url=config.base_url))
        elif self.type =="openai":
            self.openai_rerank = OpenaiReranker(config.base_url)

    async def hf_encode(self,hits:List[Tuple[str, str]]|List[List[str]]):
        # 将 Tuple 转换为 List
        hits = [list(hit) if isinstance(hit, tuple) else hit for hit in hits]
        if not hits or len(hits)==0:
            return None
        scores = None  # 初始化 scores 变量
        query = hits[0][0]
        texts = [hit[1] for hit in hits]

        try:
            if self.type == "hf_inference":
                scores = await self.model(hits)
            elif self.type =="TEI":
                if self.tei_client:
                    results = await self.tei_client.arerank(query=query,texts=texts)
                    scores = [i["score"] for i in results]
                    await self.tei_client.close()
            elif self.type =="openai":
                results = await self.openai_rerank(query=query,texts=texts)
                scores = [i.score for i in results]
                
        except Exception as e:
            logger.error(f"{type(self).__name__} Failed to get scores: {e}")
        return scores


    async def __call__(self, input: List[Tuple[str, str]]) -> Any:
        # if len(input)>32:
        #     input = input[:31]
        scores = await self.hf_encode(input)
        return scores

async def main():
    async with TEIEmbedding(TEIEmbeddingConfig(base_url="http://172.16.8.200:8086")) as client:
        # 调用rerank服务  
        texts = [  
            "Deep learning is a subset of machine learning.",  
            "Deep learning uses neural networks with many layers.",  
            "Machine learning is a field of artificial intelligence."  
        ]  
        ranks =await client.arerank("What is deep learning?", texts)  
        print("Rerank结果:")  
        for rank in ranks:  
            print(f"索引: {rank['index']}, 分数: {rank['score']}, 文本: {rank['text']}")

        rerank = Reranker({
            'base_url': 'http://172.16.8.200:8086',
            'type': 'TEI'
        })

        scores = await rerank(input=[("What is deep learning?","Deep learning is a subset of machine learning."),
                    ("What is deep learning?","Deep learning uses neural networks with many layers."),
                    ("What is deep learning?","Machine learning is a field of artificial intelligence.")])

        print("Rerank结果:")
        print(scores)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
