import asyncio
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Literal

import aiohttp
import requests
import yaml  # 需要安装 PyYAML
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from dict_transformer import DictTransformer, TransformConfig
# ================== 配置模型 (Pydantic V2) ==================

class RetryConfig(BaseModel):
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_status_codes: List[int] = [500, 502, 503, 504]

class Endpoint(BaseModel):
    name: str
    path: str
    method: Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] = 'GET'
    description: Optional[str] = None
    default_params: Optional[Dict[str, Any]] = None
    default_headers: Optional[Dict[str, str]] = None
    timeout: int = 30  # 默认 30秒

    @field_validator('method')
    @classmethod
    def upper_case_method(cls, v: str) -> str:
        return v.upper()

class ServiceConfig(BaseModel):
    base_url: str
    endpoints: List[Endpoint]
    global_headers: Dict[str, str] = Field(default_factory=dict)
    retry_config: RetryConfig = Field(default_factory=RetryConfig)

    @field_validator('base_url')
    @classmethod
    def clean_base_url(cls, v: str) -> str:
        """
        清洗 Base URL:
        1. 去除首尾空格
        2. 自动补全 http:// (如果缺失)
        3. 去除尾部斜杠 (保证标准化)
        """
        v = v.strip()
        # [NEW] 自动补全协议头
        if not v.startswith(('http://', 'https://')):
            v = f"http://{v}"
        return v.rstrip('/')

# ================== 核心客户端 ==================

class ApiClient:
    def __init__(self, config: Union[Dict, str, Path]):
        """
        初始化客户端
        :param config: 配置文件路径(str/Path) 或 配置字典(Dict)
        """
        self.config = self._load_config(config)
        self._endpoint_map = {ep.name: ep for ep in self.config.endpoints}
        
        # 异步 Session (懒加载)
        self._session: Optional[aiohttp.ClientSession] = None

    # --- 生命周期管理 (Async Context Manager) ---
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # 设置全局的连接超时，而不是请求超时
            connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    # --- 内部辅助方法 ---

    def _load_config(self, config_source: Union[Dict, str, Path]) -> ServiceConfig:
        if isinstance(config_source, (str, Path)):
            path = Path(config_source)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix in ['.yml', '.yaml']:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
            return ServiceConfig.model_validate(data)
        
        return ServiceConfig.model_validate(config_source)

    def _build_url(self, endpoint: Endpoint, path_params: Dict[str, Any] = None) -> str:
        # 1. 替换路径参数 (如 /users/{id})
        raw_path = endpoint.path
        if path_params:
            for key, value in path_params.items():
                safe_val = urllib.parse.quote(str(value))
                raw_path = raw_path.replace(f'{{{key}}}', safe_val)
        
        # 2. 标准化处理
        # 确保 path 以 / 开头
        if not raw_path.startswith('/'):
            raw_path = f"/{raw_path}"
            
        base = self.config.base_url
        
        # [NEW] 智能去重逻辑
        # 如果 base_url 结尾已经包含了 path 的开头部分，尝试去重
        # 场景: base="http://api.com/v1", path="/v1/users" -> "http://api.com/v1/users"
        # 简单的字符串重叠检测比较复杂，通常对于通用 Client，我们采用“信任配置”原则。
        # 但我们可以防止最傻的错误：
        
        # 策略：直接拼接，依赖 ServiceConfig 保证 base 无尾杠，这里保证 path 有头杠
        # 结果就是 http://host/api + /users
        
        return f"{base}{raw_path}"

    def _merge_headers(self, endpoint: Endpoint, runtime_headers: Dict = None, token: str = None) -> Dict:
        headers = self.config.global_headers.copy()
        if endpoint.default_headers:
            headers.update(endpoint.default_headers)
        if runtime_headers:
            headers.update(runtime_headers)
        if token:
            headers['Authorization'] = f"Bearer {token}"
        return headers

    def _prepare_request(self, endpoint_name: str, **kwargs) -> tuple:
        """统一处理参数，供 sync 和 async 使用"""
        if endpoint_name not in self._endpoint_map:
            raise ValueError(f"Endpoint '{endpoint_name}' not defined.")
        
        ep = self._endpoint_map[endpoint_name]
        
        # 1. 构建 URL
        url = self._build_url(ep, kwargs.get('path_params'))
        
        # 2. 合并 Headers
        headers = self._merge_headers(ep, kwargs.get('headers'), kwargs.get('token'))
        
        # 3. 合并 Query Params
        params = (ep.default_params or {}).copy()
        if kwargs.get('params'):
            params.update(kwargs['params'])
            
        # 4. 准备请求参数包
        req_kwargs = {
            'method': ep.method,
            'url': url,
            'headers': headers,
            'timeout': kwargs.get('timeout', ep.timeout),
        }
        
        # 只有在有值时才设置，避免冲突
        if params:
            req_kwargs['params'] = params
        if kwargs.get('json'):
            req_kwargs['json'] = kwargs['json']
        if kwargs.get('data'): # 支持 form-data
            req_kwargs['data'] = kwargs['data']

        return ep, req_kwargs

    # --- 核心调用方法 ---

    async def request(self, endpoint_name: str, 
                      json: Dict = None, 
                      params: Dict = None,
                      path_params: Dict = None,
                      headers: Dict = None,
                      token: str = None,
                      **kwargs) -> Dict[str, Any]:
        """
        异步调用接口 (推荐)
        """
        ep, req_kwargs = self._prepare_request(endpoint_name, json=json, params=params, 
                                               path_params=path_params, headers=headers, token=token, **kwargs)
        
        session = self._get_session()
        retry_cfg = self.config.retry_config
        
        # 处理 aiohttp 的参数差异 (aiohttp request 方法签名)
        method = req_kwargs.pop('method')
        url = req_kwargs.pop('url')
        # timeout 需要转为 ClientTimeout 对象
        req_kwargs['timeout'] = aiohttp.ClientTimeout(total=req_kwargs['timeout'])

        for attempt in range(retry_cfg.max_retries):
            try:
                async with session.request(method, url, **req_kwargs) as resp:
                    # 如果状态码在重试列表中，抛出异常以触发重试
                    if resp.status in retry_cfg.retry_status_codes:
                        resp.raise_for_status()
                    
                    # 尝试解析 JSON
                    try:
                        return await resp.json()
                    except:
                        return {"text": await resp.text(), "status": resp.status}
                        
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == retry_cfg.max_retries - 1:
                    logger.error(f"[Async] Max retries for {endpoint_name}: {e}")
                    raise
                
                wait = retry_cfg.retry_delay * (2 ** attempt) # 指数退避
                logger.warning(f"[Async] Retry {attempt+1} for {endpoint_name} due to {e}")
                await asyncio.sleep(wait)
            except Exception as e:
                # 逻辑错误不重试
                logger.error(f"[Async] Logic error in {endpoint_name}: {e}")
                raise

    def request_sync(self, endpoint_name: str, 
                     json: Dict = None, 
                     params: Dict = None,
                     path_params: Dict = None,
                     headers: Dict = None,
                     token: str = None,
                     **kwargs) -> Dict[str, Any]:
        """
        同步调用接口 (基于 requests)
        """
        ep, req_kwargs = self._prepare_request(endpoint_name, json=json, params=params, 
                                               path_params=path_params, headers=headers, token=token, **kwargs)
        
        retry_cfg = self.config.retry_config
        method = req_kwargs.pop('method')
        url = req_kwargs.pop('url')

        for attempt in range(retry_cfg.max_retries):
            try:
                resp = requests.request(method, url, **req_kwargs)
                
                if resp.status_code in retry_cfg.retry_status_codes:
                    resp.raise_for_status()
                
                try:
                    return resp.json()
                except:
                    return {"text": resp.text, "status": resp.status_code}

            except requests.RequestException as e:
                if attempt == retry_cfg.max_retries - 1:
                    logger.error(f"[Sync] Max retries for {endpoint_name}: {e}")
                    raise
                
                wait = retry_cfg.retry_delay * (2 ** attempt)
                logger.warning(f"[Sync] Retry {attempt+1} for {endpoint_name} due to {e}")
                time.sleep(wait)

    async def request_batch(
        self, 
        endpoint_name: str, 
        requests_data: List[Dict[str, Any]], 
        concurrency: int = 10,
        return_exceptions: bool = True,
        **common_kwargs
    ) -> List[Any]:
        """
        [新增] 并发批处理请求
        
        :param endpoint_name: 调用的 Endpoint 名称
        :param requests_data: 请求参数列表，每个元素是一个字典，包含该次请求特有的参数 
                              (如 {'json': {...}}, {'path_params': {'id': 1}})
        :param concurrency: 并发控制 (信号量大小)
        :param return_exceptions: True则返回异常对象，False则遇到错误直接抛出中断
        :param common_kwargs: 所有请求共用的参数 (如 headers, token, timeout)
        
        :return: 结果列表，顺序与 requests_data 一致
        """
        if not requests_data:
            return []

        # 1. 创建信号量
        sem = asyncio.Semaphore(concurrency)

        # 2. 定义单个任务的 Worker
        async def worker(req_specific_kwargs: Dict[str, Any]):
            async with sem:
                # 合并参数：公共参数 (common_kwargs) + 特有参数 (req_specific_kwargs)
                # 特有参数优先级更高，覆盖公共参数
                final_kwargs = {**common_kwargs, **req_specific_kwargs}
                
                # 调用现有的单次请求逻辑 (它包含了重试、URL构建、Session管理)
                return await self.request(endpoint_name, **final_kwargs)

        # 3. 创建任务列表
        tasks = [worker(data) for data in requests_data]

        # 4. 并发执行
        logger.info(f"Starting batch request to '{endpoint_name}' (Total: {len(tasks)}, Concurrency: {concurrency})")
        results = await asyncio.gather(*tasks, return_exceptions=return_exceptions)
        
        # 5. 简单的结果统计日志
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Batch '{endpoint_name}' finished. Success: {success_count}/{len(results)}")
        
        return results
    
class ApiClientFactory:
    """
    客户端工厂：用于管理多个服务的 ApiClient 实例
    实现了单例注册表模式
    """
    _clients: Dict[str, ApiClient] = {}

    @classmethod
    def create(cls, name: str, config: Union[Dict, str, Path]) -> ApiClient:
        """创建并注册一个客户端"""
        if name in cls._clients:
            logger.warning(f"ApiClient '{name}' already exists. Overwriting.")
            # 如果覆盖，先关闭旧的
            old_client = cls._clients[name]
            # 注意：这里无法await，只能依赖垃圾回收或显式关闭，
            # 建议在应用初始化阶段完成所有创建
        
        client = ApiClient(config)
        cls._clients[name] = client
        return client

    @classmethod
    def get(cls, name: str) -> ApiClient:
        """获取已注册的客户端"""
        client = cls._clients.get(name)
        if not client:
            raise KeyError(f"ApiClient '{name}' not found. Did you register it?")
        return client

    @classmethod
    def register_from_files(cls, config_map: Dict[str, Union[str, Path]]):
        """
        批量注册，例如：
        ApiClientFactory.register_from_files({
            "user_service": "configs/user_api.yaml",
            "order_service": "configs/order_api.json"
        })
        """
        for name, path in config_map.items():
            cls.create(name, path)

    @classmethod
    async def close_all(cls):
        """
        【重要】应用退出时调用，关闭所有客户端的 Session
        """
        logger.info("Closing all ApiClients...")
        close_tasks = []
        for name, client in cls._clients.items():
            close_tasks.append(client.close())
        
        if close_tasks:
            await asyncio.gather(*close_tasks)
        cls._clients.clear()
        logger.info("All ApiClients closed.")