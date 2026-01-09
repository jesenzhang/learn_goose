import aiohttp
import asyncio
from loguru import logger
import json
from typing import Dict, Any, List, Optional, Union
import os
import requests
from dataclasses import dataclass
import time
from pydantic import BaseModel, Field


class RequestConfig(BaseModel):
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    header: Optional[Dict[str, str]] = None

class APIToolConfig(BaseModel):
    base_url:Optional[str]=None
    router:Optional[str]=None
    config:Optional[RequestConfig]=None

class APITool:
    @classmethod
    def from_dict(cls,dict_obj:dict):
        config = APIToolConfig.model_validate(dict_obj)
        return APITool(base_url=config.base_url,router = config.router,config=config.config)
    
    @classmethod
    def from_config(cls,config:APIToolConfig):
        return APITool(base_url=config.base_url,router = config.router,config=config.config)

    def __init__(self, base_url: str, router:Optional[str]=None,config: Union[RequestConfig, Dict] = None):
        self.base_url = base_url.rstrip('/') if base_url else ''
        if router:
            self.router = f'/{router}' if not router.startswith('/') else router
        else:
            self.router = None
        if isinstance(config, dict):
            self.config = RequestConfig(**config)
        else:
            self.config = config or RequestConfig()
        
    def _build_url(self, router: Optional[str] = None) -> str:
        """统一构建URL"""
        url = self.base_url
        if self.router:
            url = f"{url}/{self.router.lstrip('/')}"
        if router:
            return f"{url}/{router.lstrip('/')}"
        return url

    async def is_api_available(self) -> bool:
        """检查API是否可用"""
        try:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(self.base_url) as resp:
                    return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def _request_with_retry(self, method: str, **kwargs) -> Dict[str, Any]:
        """带重试机制的请求方法"""
        for attempt in range(self.config.max_retries):
            try:
                if method == 'get':
                    return await self._get_async(**kwargs)
                elif method == 'post':
                    return await self._post_async(**kwargs)
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(self.config.retry_delay)
                logger.warning(f"Retry {attempt + 1}/{self.config.max_retries} after error: {e}")

    async def _post_async(self, query: Dict, router: Optional[str] = None, 
                        params=None, token=None) -> Dict[str, Any]:
        """内部POST请求实现"""
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {'Content-Type': 'application/json'}
            headers.update(self.config.header or {})
            if token:
                headers['Authorization'] = f'{token}'
                
            async with session.post(
                self._build_url(router),
                params=params,
                json=query,
                headers=headers
            ) as resp:
                return await resp.json()

    async def post_async(self, query: Dict, router: Optional[str] = None, 
                        params=None, token=None) -> Dict[str, Any]:
        """异步POST请求"""
        try:
            return await self._request_with_retry(
                'post', query=query, router=router, params=params, token=token
            )
        except Exception as e:
            logger.error(f"Post request failed: {e}")
            return {"error": str(e)}

    async def _get_async(self, router: Optional[str] = None, 
                        params=None, token=None) -> Dict[str, Any]:
        """内部GET请求实现"""
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {}
            headers.update(self.config.header or {})
            if token:
                headers['Authorization'] = f'{token}'
                
            async with session.get(
                self._build_url(router),
                params=params,
                headers=headers
            ) as resp:
                return await resp.json()

    async def get_async(self, router: Optional[str] = None, 
                       params=None, token=None) -> Dict[str, Any]:
        """异步GET请求"""
        try:
            return await self._request_with_retry(
                'get', router=router, params=params, token=token
            )
        except Exception as e:
            logger.error(f"Get request failed: {e}")
            return {"error": str(e)}

    def post_sync(self, query: Dict, router: Optional[str] = None, 
                 params=None, token=None) -> Dict[str, Any]:
        """同步POST请求"""
        for attempt in range(self.config.max_retries):
            try:
                headers = {'Content-Type': 'application/json'}
                headers.update(self.config.header or {})
                if token:
                    headers['Authorization'] = f'{token}'
                    
                response = requests.post(
                    self._build_url(router),
                    params=params,
                    json=query,
                    headers=headers,
                    timeout=self.config.timeout
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    logger.error(f"Post request failed: {e}")
                    return {"error": str(e)}
                time.sleep(self.config.retry_delay)
                logger.warning(f"Retry {attempt + 1}/{self.config.max_retries} after error: {e}")

    def get_sync(self, router: Optional[str] = None, 
                params=None, token=None) -> Dict[str, Any]:
        """同步GET请求"""
        for attempt in range(self.config.max_retries):
            try:
                headers = {}
                headers.update(self.config.header or {})
                if token:
                    headers['Authorization'] = f'{token}'
                    
                response = requests.get(
                    self._build_url(router),
                    params=params,
                    headers=headers,
                    timeout=self.config.timeout
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    logger.error(f"Get request failed: {e}")
                    return {"error": str(e)}
                time.sleep(self.config.retry_delay)
                logger.warning(f"Retry {attempt + 1}/{self.config.max_retries} after error: {e}")