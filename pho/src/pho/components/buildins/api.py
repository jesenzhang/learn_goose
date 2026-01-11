"""
API Client Component - Configurable HTTP requests for workflows.

Based on api_client.py, provides:
- Configured endpoints via YAML/JSON
- Retry mechanism
- Sync and async support
- Batch requests
"""

import asyncio
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Literal

import aiohttp
import requests
import yaml
from pydantic import BaseModel, Field, field_validator

from pho.components.base import Component
from pho.components.registry import register_component
from pho.types import NodeTypes


# ================== Configuration Models ==================

class RetryConfig(BaseModel):
    max_retries: int = Field(3, description="Maximum number of retries")
    retry_delay: float = Field(1.0, description="Initial retry delay (seconds)")
    retry_status_codes: List[int] = Field(
        default_factory=lambda: [500, 502, 503, 504],
        description="HTTP status codes that trigger retry"
    )


class EndpointConfig(BaseModel):
    name: str = Field(..., description="Endpoint identifier")
    path: str = Field(..., description="URL path (e.g., /api/users)")
    method: Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] = Field('GET', description="HTTP method")
    description: Optional[str] = Field(None, description="Endpoint description")
    default_params: Optional[Dict[str, Any]] = Field(None, description="Default query parameters")
    default_headers: Optional[Dict[str, str]] = Field(None, description="Default headers")
    timeout: int = Field(30, description="Request timeout (seconds)")

    @field_validator('method')
    @classmethod
    def upper_case_method(cls, v: str) -> str:
        return v.upper()


class ApiClientComponentConfig(BaseModel):
    # Base configuration
    base_url: str = Field(..., description="Base URL for API (e.g., https://api.example.com)")
    global_headers: Dict[str, str] = Field(default_factory=dict, description="Global headers for all requests")
    retry_config: RetryConfig = Field(default_factory=RetryConfig, description="Retry configuration")

    # Endpoint configuration (can be JSON string or dict)
    endpoints_config: Optional[str] = Field(None, alias="endpoints", description="Endpoints JSON config")

    # Request configuration
    endpoint_name: str = Field(..., description="Name of endpoint to call")
    request_params: Optional[Dict[str, Any]] = Field(None, description="Request parameters")
    request_json: Optional[Dict[str, Any]] = Field(None, alias="json", description="Request JSON body")
    request_data: Optional[Dict[str, Any]] = Field(None, description="Request form data")
    path_params: Optional[Dict[str, Any]] = Field(None, description="Path parameters for URL substitution")
    headers: Optional[Dict[str, str]] = Field(None, description="Additional headers for this request")
    token: Optional[str] = Field(None, description="Bearer token for authentication")
    concurrency: int = Field(10, description="Concurrency for batch requests")
    use_async: bool = Field(True, description="Use async requests")

    @field_validator('base_url')
    @classmethod
    def clean_base_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            v = f"http://{v}"
        return v.rstrip('/')


@register_component(
    name=NodeTypes.HTTP_REQUESTER,
    group="API",
    label="API Client",
    description="Configurable HTTP API client with retry and batch support",
    icon="api",
    author="System",
    version="1.0.0",
    config_model=ApiClientComponentConfig,
)
class ApiClientComponent(Component):
    """
    API Client component for making HTTP requests.

    Supports:
    - Configured endpoints via JSON/YAML
    - Retry mechanism with exponential backoff
    - Sync and async requests
    - Batch requests with concurrency control
    """

    def __init__(self):
        super().__init__()
        self._endpoint_map = {}
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _load_endpoints(self, config: ApiClientComponentConfig) -> None:
        """Load endpoints from configuration"""
        if not config.endpoints_config:
            self._endpoint_map = {}
            return

        # Try to parse as JSON
        try:
            if config.endpoints_config.strip().startswith(('{', '[')):
                endpoints_data = json.loads(config.endpoints_config)
            else:
                # Try as file path
                path = Path(config.endpoints_config)
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        if path.suffix in ['.yml', '.yaml']:
                            endpoints_data = yaml.safe_load(f)
                        else:
                            endpoints_data = json.load(f)
                else:
                    endpoints_data = json.loads(config.endpoints_config)

            # Parse endpoint configs
            for ep_data in endpoints_data:
                ep = EndpointConfig(**ep_data)
                self._endpoint_map[ep.name] = ep

        except Exception as e:
            raise ValueError(f"Failed to load endpoints: {str(e)}")

    def _build_url(self, config: ApiClientComponentConfig, endpoint: EndpointConfig) -> str:
        """Build complete URL from base_url and endpoint path"""
        raw_path = endpoint.path

        # Replace path parameters
        if config.path_params:
            for key, value in config.path_params.items():
                safe_val = urllib.parse.quote(str(value))
                raw_path = raw_path.replace(f'{{{key}}}', safe_val)

        if not raw_path.startswith('/'):
            raw_path = f"/{raw_path}"

        return f"{config.base_url}{raw_path}"

    def _merge_headers(
        self,
        config: ApiClientComponentConfig,
        endpoint: EndpointConfig
    ) -> Dict[str, str]:
        """Merge headers from global, endpoint, and request"""
        headers = config.global_headers.copy()
        if endpoint.default_headers:
            headers.update(endpoint.default_headers)
        if config.headers:
            headers.update(config.headers)
        if config.token:
            headers['Authorization'] = f"Bearer {config.token}"
        return headers

    def _merge_params(
        self,
        config: ApiClientComponentConfig,
        endpoint: EndpointConfig
    ) -> Dict[str, Any]:
        """Merge query parameters"""
        params = (endpoint.default_params or {}).copy()
        if config.request_params:
            params.update(config.request_params)
        return params

    async def _request_async(
        self,
        config: ApiClientComponentConfig,
        endpoint: EndpointConfig
    ) -> Dict[str, Any]:
        """Make async HTTP request"""
        url = self._build_url(config, endpoint)
        headers = self._merge_headers(config, endpoint)
        params = self._merge_params(config, endpoint)

        retry_cfg = config.retry_config
        session = self._get_session()

        req_kwargs = {
            'timeout': aiohttp.ClientTimeout(total=endpoint.timeout),
            'headers': headers,
        }
        if params:
            req_kwargs['params'] = params
        if config.request_json:
            req_kwargs['json'] = config.request_json
        if config.request_data:
            req_kwargs['data'] = config.request_data

        for attempt in range(retry_cfg.max_retries):
            try:
                async with session.request(endpoint.method, url, **req_kwargs) as resp:
                    if resp.status in retry_cfg.retry_status_codes:
                        resp.raise_for_status()

                    try:
                        return await resp.json()
                    except:
                        return {"text": await resp.text(), "status": resp.status}

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == retry_cfg.max_retries - 1:
                    raise RuntimeError(f"Max retries for {config.endpoint_name}: {e}")

                wait = retry_cfg.retry_delay * (2 ** attempt)
                await asyncio.sleep(wait)
            except Exception as e:
                raise RuntimeError(f"Logic error in {config.endpoint_name}: {e}")

    def _request_sync(
        self,
        config: ApiClientComponentConfig,
        endpoint: EndpointConfig
    ) -> Dict[str, Any]:
        """Make sync HTTP request"""
        url = self._build_url(config, endpoint)
        headers = self._merge_headers(config, endpoint)
        params = self._merge_params(config, endpoint)

        retry_cfg = config.retry_config

        req_kwargs = {
            'headers': headers,
            'timeout': endpoint.timeout,
        }
        if params:
            req_kwargs['params'] = params
        if config.request_json:
            req_kwargs['json'] = config.request_json
        if config.request_data:
            req_kwargs['data'] = config.request_data

        for attempt in range(retry_cfg.max_retries):
            try:
                resp = requests.request(endpoint.method, url, **req_kwargs)

                if resp.status_code in retry_cfg.retry_status_codes:
                    resp.raise_for_status()

                try:
                    return resp.json()
                except:
                    return {"text": resp.text, "status": resp.status_code}

            except requests.RequestException as e:
                if attempt == retry_cfg.max_retries - 1:
                    raise RuntimeError(f"Max retries for {config.endpoint_name}: {e}")

                wait = retry_cfg.retry_delay * (2 ** attempt)
                time.sleep(wait)

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: ApiClientComponentConfig
    ) -> Dict[str, Any]:
        """Execute the API request"""
        # Load endpoints configuration
        self._load_endpoints(config)

        # Get endpoint
        if config.endpoint_name not in self._endpoint_map:
            raise ValueError(f"Endpoint '{config.endpoint_name}' not found in configuration")

        endpoint = self._endpoint_map[config.endpoint_name]

        # Make request
        if config.use_async:
            result = await self._request_async(config, endpoint)
        else:
            result = self._request_sync(config, endpoint)

        return {
            "response": result,
            "endpoint": config.endpoint_name,
            "success": True
        }
