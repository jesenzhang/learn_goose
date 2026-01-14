import os
import json
import time
import httpx
from typing import List, Dict, Optional, Union, Any
from pydantic import BaseModel, Field
from loguru import logger
from .schema import Document
# ================= 数据模型定义 =================

class EsQuery(BaseModel):
    """ES 查询参数结构"""
    text: Union[str, List[str]]
    search_type: Optional[int] = None
    resource_type: Optional[int] = None

# ================= 基础配置与基类 =================

class SearchBaseConfig(BaseModel):
    top_k: int = 5
    timeout: float = 10.0
    proxy: Optional[str] = None  # 支持 http://... 格式

class SearchBase:
    """搜索基类，定义统一接口"""
    def __init__(self, config: Union[SearchBaseConfig, Dict]):
        if isinstance(config, dict):
            # 自动识别子类配置类型并转换
            config_cls = self._get_config_class()
            self.config = config_cls.model_validate(config)
        else:
            self.config = config
        
        # === [修复]：动态构建参数，防止传入 None 或不支持的参数 ===
        self.client_kwargs = {}
        
        # 1. 设置超时
        if self.config.timeout is not None:
            self.client_kwargs["timeout"] = self.config.timeout
            
        # 2. 设置代理 (适配 httpx 0.24+)
        # httpx 新版使用 'proxy' (单数)，且值通常为字符串 URL (例如 "http://127.0.0.1:7890")
        if self.config.proxy:
            self.client_kwargs["proxy"] = self.config.proxy

    def _get_config_class(self):
        return SearchBaseConfig

    async def search_async(self, query: Any, **kwargs) -> Any:
        raise NotImplementedError("Subclasses must implement search_async")

    async def close(self):
        """资源清理接口"""
        if hasattr(self, 'client') and self.client:
            await self.client.aclose()
# ================= 1. Web Search (Bing) =================

class WebSearchConfig(SearchBaseConfig):
    endpoint: str = "https://api.bing.microsoft.com/v7.0/search"
    subscription_key: str = Field(default="", description="Bing Search Key")
    # 如果为了兼容旧代码保留硬编码，建议移至环境变量
    update_key_password: str = "ChatHDUpdateBingKey" 
    use_cache: bool = False
    cache_dir: List[str] = ["logs/web"]

class WebSearch(SearchBase):
    def __init__(self, config: Union[WebSearchConfig, Dict]):
        super().__init__(config)
        self.config: WebSearchConfig = self.config # 类型提示
        self.cache_data = self._load_cache() if self.config.use_cache else {}
        # 保持长连接
        self.client = httpx.AsyncClient(**self.client_kwargs)

    def _get_config_class(self):
        return WebSearchConfig

    def _load_cache(self) -> Dict[str, Any]:
        """加载本地缓存文件"""
        results = {}
        try:
            for log_dir in self.config.cache_dir:
                if not os.path.exists(log_dir): continue
                for fname in sorted(os.listdir(log_dir)):
                    fpath = os.path.join(log_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                if "Web Search Result: " in line:
                                    json_str = line.split("Web Search Result: ")[-1].strip()
                                    data = json.loads(json_str)
                                    if "queryContext" in data:
                                        q = data["queryContext"].get("originalQuery", "").strip()
                                        if q: results[q] = data
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Failed to load web cache: {e}")
        return results

    async def search_async(self, query: str, **kwargs) -> List[Document]:
        query = query.strip()
        if not query: return []

        # 1. 查缓存
        if self.config.use_cache and query in self.cache_data:
            logger.info(f"Hit Web Cache for: {query}")
            return self._parse_bing_result(self.cache_data[query])

        # 2. 发起请求
        headers = {"Ocp-Apim-Subscription-Key": kwargs.get("subscription_key", self.config.subscription_key)}
        params = {"q": query, "mkt": "zh-CN", "count": self.config.top_k}

        try:
            resp = await self.client.get(self.config.endpoint, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            # 记录日志 (保持原有逻辑)
            logger.bind(web_result=True).debug(f"Web Search Result: {json.dumps(data, ensure_ascii=False)}")
            
            return self._parse_bing_result(data)
        except Exception as e:
            logger.error(f"Web Search Failed: {e}")
            return []

    def _parse_bing_result(self, data: Dict) -> List[Document]:
        """统一解析 Bing 返回格式"""
        docs = []
        try:
            items = data.get("webPages", {}).get("value", [])
            for item in items[:self.config.top_k]:
                content = f"{item.get('name', '')}\n{item.get('snippet', '')}"
                # 简单过滤逻辑
                if "疯了" in content and "桂宝" in content: continue
                
                doc = Document(
                    page_content=content,
                    metadata={
                        "source": "网络搜索",
                        "filepath": item.get("url"),
                        "title": item.get("name")
                    }
                )
                docs.append(doc)
        except Exception as e:
            logger.error(f"Parse Bing Error: {e}")
        return docs

    async def close(self):
        await self.client.aclose()

# ================= 2. API Search (Internal Service) =================

class APISearchConfig(SearchBaseConfig):
    # 基础地址，不带路径
    base_url: str = "http://192.168.10.198:9980" 
    # 默认路由
    default_router: str = "/gzcapi/search/search_data?p=ai"

class APISearch(SearchBase):
    def __init__(self, config: Union[APISearchConfig, Dict]):
        super().__init__(config)
        self.config: APISearchConfig = self.config
        # 使用 AsyncClient 复用连接池
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            **self.client_kwargs
        )

    def _get_config_class(self):
        return APISearchConfig

    async def _request_wrapper(self, method: str, url: str, **kwargs) -> Dict:
        """统一的请求包装器，处理错误和日志"""
        start_time = time.time()
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            data = response.json()
            
            elapsed = time.time() - start_time
            logger.info(f"{method.upper()} {url} Cost: {elapsed:.2f}s")
            
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Error {e.response.status_code} for {url}: {e}")
            return {"status": 0, "error": f"HTTP {e.response.status_code}"}
        except httpx.RequestError as e:
            logger.error(f"Connection Error to {url}: {e}")
            return {"status": 0, "error": "Connection Failed"}
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON response from {url}")
            return {"status": 0, "error": "Invalid JSON"}
        except Exception as e:
            logger.error(f"Unexpected Error: {e}")
            return {"status": 0, "error": str(e)}

    async def search_async(self, query: Dict, params: Dict = None, token: str = None) -> Dict:
        """
        发送 POST 搜索请求
        :param query: 请求体 JSON 数据 (通常是 EsQuery.model_dump())
        :param params: URL 参数
        """
        headers = {'Content-Type': 'application/json'}
        if token: headers['Authorization'] = token

        # 这里的 url 只需要传路径，因为 base_url 已经在 client 中设置
        return await self._request_wrapper(
            "POST", 
            self.config.default_router, 
            json=query, 
            params=params, 
            headers=headers
        )

    async def get_async(self, params: Dict = None, token: str = None) -> Dict:
        """发送 GET 请求"""
        headers = {}
        if token: headers['Authorization'] = token

        return await self._request_wrapper(
            "GET", 
            self.config.default_router, 
            params=params, 
            headers=headers
        )

    async def close(self):
        """显式关闭客户端"""
        await self.client.aclose()