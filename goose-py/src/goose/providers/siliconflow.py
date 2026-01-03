from typing import List, Optional, Dict, Any
from goose.providers.openai import OpenAIProvider
from goose.providers.factory import ProviderFactory
from goose.providers.types import RerankResult

@ProviderFactory.register("siliconflow")
class SiliconFlowProvider(OpenAIProvider):
    """
    SiliconFlow (硅基流动) Provider
    本质上是 OpenAI 协议，但有特定的默认 Base URL
    """
    def __init__(self, model_config: Dict[str, Any]):
        # 强制设置 Base URL，除非用户显式覆盖
        if "base_url" not in model_config:
            model_config["base_url"] = "https://api.siliconflow.cn/v1"
            
        super().__init__(model_config)
    

    async def rerank(
        self, 
        query: str, 
        documents: List[str], 
        top_n: Optional[int] = None
    ) -> List[RerankResult]:
        """
        调用 SiliconFlow 的 Rerank API
        Endpoint: POST /v1/rerank
        """
        if not documents:
            return []

        # Rerank 模型通常不同于 Chat 模型
        rerank_model = self.model_config.model_name or "BAAI/bge-reranker-v2-m3"
        
        payload = {
            "model": rerank_model,
            "query": query,
            "documents": documents,
            "top_n": top_n or len(documents),
            "return_documents": False # 仅返回分数和索引，减少流量
        }

        try:
            # 使用 AsyncOpenAI client 内部的 _client (httpx.AsyncClient) 发送原始请求
            # 或者使用 client.post (如果是较新版本的 SDK)
            # 这里使用通用的 httpx 方式，复用 client 的 header 和 api_key
            
            # 注意：OpenAI SDK 的 client.post 是隐藏方法，直接拼接 URL 请求更稳妥
            response = await self.client.post(
                path="/rerank", 
                body=payload,
                cast_to=object # 我们自己解析 JSON
            )
            
            # response 是一个 object，如果是 cast_to=object，通常是 dict 或 UnparsedResponse
            # 在 OpenAI SDK v1+ 中，.post 返回的是响应对象，我们需要 .model_dump() 或者直接作为 dict
            
            # 假设 response 已经是解析好的 Dict (视 SDK 版本而定)
            # 如果 response 是 httpx.Response，则需要 response.json()
            
            # 为了适配最广泛的情况，我们可以直接用 requests 逻辑，或者复用 SDK：
            # SiliconFlow 返回格式:
            # { "results": [ {"index": 0, "relevance_score": 0.9}, ... ] }
            
            # 这里做个防御性转换，因为 SDK 的泛型比较复杂
            if hasattr(response, "results"):
                results_data = response.results
            elif isinstance(response, dict):
                results_data = response.get("results", [])
            else:
                # 兜底：假设是 Pydantic 模型
                results_data = getattr(response, "results", [])

            formatted_results = []
            for item in results_data:
                # 兼容不同的字段名 (score vs relevance_score)
                score = getattr(item, "relevance_score", getattr(item, "score", 0.0))
                index = getattr(item, "index", 0)
                
                formatted_results.append(RerankResult(
                    index=index,
                    score=score,
                    relevance_score=score,
                    document=documents[index] # 重新根据索引回填文档内容
                ))
            
            # 按分数降序排列
            formatted_results.sort(key=lambda x: x.score, reverse=True)
            return formatted_results

        except Exception as e:
            self._handle_error(e)
            return []