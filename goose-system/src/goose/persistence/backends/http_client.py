"""
HTTP API Client for Database Operations

This module provides a client for communicating with a unified HTTP API backend
for database operations. It handles authentication, error handling, and response parsing.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import json
import asyncio

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

    class httpx:
        class AsyncClient:
            def __init__(self, *args, **kwargs):
                raise ImportError(
                    "httpx is required for HTTPBackend. "
                    "Install it with: pip install httpx"
                )

        class HTTPStatusError(Exception):
            pass

        class TimeoutException(Exception):
            pass


logger = logging.getLogger(__name__)


@dataclass
class HttpClientConfig:
    """Configuration for HTTP API client"""
    base_url: str
    api_key: Optional[str] = None
    api_key_header: str = "X-API-Key"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 0.5
    headers: Dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True


class HttpClientError(Exception):
    """Error raised by HTTP client operations"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Any = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class HttpClient:
    """
    HTTP Client for Database API Operations

    Provides methods for all database operations through a unified HTTP API.
    """

    ENDPOINTS = {
        "boot": "/api/v1/db/boot",
        "insert": "/api/v1/db/{table}/insert",
        "get": "/api/v1/db/{table}/get",
        "get_batch": "/api/v1/db/{table}/get-batch",
        "find": "/api/v1/db/{table}/find",
        "count": "/api/v1/db/{table}/count",
        "update": "/api/v1/db/{table}/update",
        "update_by": "/api/v1/db/{table}/update-by",
        "upsert": "/api/v1/db/{table}/upsert",
        "delete": "/api/v1/db/{table}/delete",
        "delete_by": "/api/v1/db/{table}/delete-by",
        "transaction_begin": "/api/v1/db/transaction/begin",
        "transaction_commit": "/api/v1/db/transaction/{transaction_id}/commit",
        "transaction_rollback": "/api/v1/db/transaction/{transaction_id}/rollback",
    }

    def __init__(self, config: HttpClientConfig):
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for HTTPBackend. "
                "Install it with: pip install httpx"
            )

        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._transaction_id: Optional[str] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                **self.config.headers,
            }
            if self.config.api_key:
                headers[self.config.api_key_header] = self.config.api_key

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=headers,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
            )
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_url(self, endpoint: str, **kwargs) -> str:
        """Get full URL for an endpoint"""
        url = self.ENDPOINTS.get(endpoint, endpoint)
        return url.format(**kwargs)

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Any:
        """Make HTTP request with retry logic"""
        url = self._get_url(endpoint, **kwargs.get("path_params", {}))

        if self._transaction_id:
            request_data = kwargs.get("json", {})
            request_data["_transaction_id"] = self._transaction_id
            kwargs["json"] = request_data

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                client = await self._get_client()
                response = await client.request(method, url, **kwargs)

                if response.status_code < 400:
                    if response.status_code == 204:
                        return None
                    return response.json()

                response.raise_for_status()

            except httpx.HTTPStatusError as e:
                last_error = e
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    error_data = e.response.text
                    try:
                        error_data = e.response.json()
                    except:
                        pass
                    raise HttpClientError(
                        f"HTTP {e.response.status_code}: {error_data}",
                        status_code=e.response.status_code,
                        response_data=error_data
                    )
                logger.warning(f"HTTP error (attempt {attempt + 1}/{self.config.max_retries}): {e}")

            except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(f"Timeout (attempt {attempt + 1}/{self.config.max_retries}): {e}")

            except httpx.NetworkError as e:
                last_error = e
                logger.warning(f"Network error (attempt {attempt + 1}/{self.config.max_retries}): {e}")

            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))

        raise HttpClientError(f"Request failed after {self.config.max_retries} attempts: {last_error}")

    async def boot(self, schemas: List[Dict]) -> Dict:
        return await self._request(
            "POST",
            "boot",
            json={"schemas": schemas}
        )

    async def insert(self, table: str, data: Dict) -> Dict:
        return await self._request(
            "POST",
            "insert",
            path_params={"table": table},
            json={"data": data}
        )

    async def get(self, table: str, pk_value: Any) -> Optional[Dict]:
        response = await self._request(
            "POST",
            "get",
            path_params={"table": table},
            json={"pk_value": pk_value}
        )
        return response.get("data") if response else None

    async def get_batch(self, table: str, pk_values: List[Any]) -> List[Dict]:
        response = await self._request(
            "POST",
            "get_batch",
            path_params={"table": table},
            json={"pk_values": pk_values}
        )
        return response.get("data", []) if response else []

    async def find(
        self,
        table: str,
        filters: Dict,
        limit: int = -1,
        offset: int = 0
    ) -> List[Dict]:
        response = await self._request(
            "POST",
            "find",
            path_params={"table": table},
            json={
                "filters": filters,
                "limit": limit,
                "offset": offset
            }
        )
        return response.get("data", []) if response else []

    async def count(self, table: str, filters: Dict) -> int:
        response = await self._request(
            "POST",
            "count",
            path_params={"table": table},
            json={"filters": filters}
        )
        return response.get("count", 0) if response else 0

    async def update(self, table: str, pk_value: Any, data: Dict) -> Dict:
        return await self._request(
            "POST",
            "update",
            path_params={"table": table},
            json={
                "pk_value": pk_value,
                "data": data
            }
        )

    async def update_by(self, table: str, filters: Dict, data: Dict) -> int:
        response = await self._request(
            "POST",
            "update_by",
            path_params={"table": table},
            json={
                "filters": filters,
                "data": data
            }
        )
        return response.get("affected_rows", 0) if response else 0

    async def upsert(self, table: str, data: Dict) -> Dict:
        return await self._request(
            "POST",
            "upsert",
            path_params={"table": table},
            json={"data": data}
        )

    async def delete(self, table: str, pk_value: Any) -> Dict:
        return await self._request(
            "POST",
            "delete",
            path_params={"table": table},
            json={"pk_value": pk_value}
        )

    async def delete_by(self, table: str, filters: Dict) -> int:
        response = await self._request(
            "POST",
            "delete_by",
            path_params={"table": table},
            json={"filters": filters}
        )
        return response.get("affected_rows", 0) if response else 0

    async def begin_transaction(self) -> str:
        response = await self._request(
            "POST",
            "transaction_begin",
            json={}
        )
        self._transaction_id = response.get("transaction_id")
        return self._transaction_id

    async def commit_transaction(self) -> None:
        if not self._transaction_id:
            raise HttpClientError("No active transaction to commit")

        await self._request(
            "POST",
            "transaction_commit",
            path_params={"transaction_id": self._transaction_id},
            json={}
        )
        self._transaction_id = None

    async def rollback_transaction(self) -> None:
        if not self._transaction_id:
            raise HttpClientError("No active transaction to rollback")

        await self._request(
            "POST",
            "transaction_rollback",
            path_params={"transaction_id": self._transaction_id},
            json={}
        )
        self._transaction_id = None

    @property
    def in_transaction(self) -> bool:
        return self._transaction_id is not None


def create_http_client(
    base_url: str,
    api_key: Optional[str] = None,
    **kwargs
) -> HttpClient:
    """Factory function to create HTTP client"""
    config = HttpClientConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        **kwargs
    )
    return HttpClient(config)
