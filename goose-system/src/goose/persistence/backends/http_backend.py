"""
HTTP Backend for Persistence Layer

This module provides a backend implementation that communicates with a unified
HTTP API for database operations. Useful for scenarios where database access
needs to go through a centralized service.
"""

import logging
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from contextlib import asynccontextmanager

from ..backend import PersistenceBackend
from ..spec import TableSpec
from .http_client import HttpClient, HttpClientError, create_http_client, HttpClientConfig


logger = logging.getLogger(__name__)


def parse_db_url(db_url: str) -> tuple[str, Optional[str], dict]:
    """Parse database URL for HTTP backend"""
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(db_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    query_params = parse_qs(parsed.query)

    api_key = None
    if "api_key" in query_params:
        api_key = query_params["api_key"][0]

    config_kwargs = {}
    for key, values in query_params.items():
        if key == "api_key":
            continue
        value = values[0]
        if key == "timeout":
            config_kwargs[key] = float(value)
        elif key == "max_retries":
            config_kwargs[key] = int(value)
        elif key == "retry_delay":
            config_kwargs[key] = float(value)
        elif key == "verify_ssl":
            config_kwargs[key] = value.lower() in ("true", "1", "yes")
        else:
            config_kwargs[key] = value

    return base_url, api_key, config_kwargs


class HTTPBackend(PersistenceBackend):
    """HTTP API Backend for persistence operations"""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        **config_kwargs
    ):
        self.config = HttpClientConfig(
            base_url=base_url,
            api_key=api_key,
            **config_kwargs
        )
        self.client = create_http_client(base_url, api_key, **config_kwargs)
        self._connected = False

    async def boot(self, schemas: List[Union[str, List[str]]]):
        if self._connected:
            logger.warning("HTTPBackend already booted")
            return

        try:
            api_schemas = []
            for s in schemas:
                if isinstance(s, dict):
                    api_schemas.append(s)
                elif isinstance(s, TableSpec):
                    api_schemas.append({
                        "table_name": s.table_name,
                        "schema_sql": s.schema_sql,
                        "pk_field": s.pk_field,
                        "priority": s.priority,
                        "source": s.source,
                    })
                elif isinstance(s, str):
                    api_schemas.append({"schema_sql": s})
                elif isinstance(s, list):
                    for item in s:
                        if isinstance(item, str):
                            api_schemas.append({"schema_sql": item})

            await self.client.boot(api_schemas)
            self._connected = True
            logger.info(f"HTTPBackend: Booted successfully with {len(schemas)} tables")
        except HttpClientError as e:
            logger.error(f"HTTPBackend boot failed: {e}")
            raise

    async def insert(self, spec: TableSpec, data: Dict[str, Any]) -> None:
        await self.client.insert(spec.table_name, data)

    async def get(self, spec: TableSpec, pk_value: Any) -> Optional[Dict]:
        result = await self.client.get(spec.table_name, pk_value)
        return result

    async def get_batch(self, spec: TableSpec, pk_values: List[Any]) -> List[Dict]:
        if not pk_values:
            return []
        return await self.client.get_batch(spec.table_name, pk_values)

    async def find(
        self,
        spec: TableSpec,
        filters: Dict[str, Any],
        limit: int = -1,
        offset: int = 0
    ) -> List[Dict]:
        return await self.client.find(spec.table_name, filters, limit, offset)

    async def count(self, spec: TableSpec, filters: Dict[str, Any]) -> int:
        return await self.client.count(spec.table_name, filters)

    async def update(self, spec: TableSpec, pk_value: Any, data: Dict[str, Any]) -> None:
        await self.client.update(spec.table_name, pk_value, data)

    async def update_by(
        self,
        spec: TableSpec,
        filters: Dict[str, Any],
        data: Dict[str, Any]
    ) -> int:
        if not filters:
            raise ValueError("update_by requires filters")
        return await self.client.update_by(spec.table_name, filters, data)

    async def upsert(self, spec: TableSpec, data: Dict[str, Any]) -> None:
        await self.client.upsert(spec.table_name, data)

    async def delete(self, spec: TableSpec, pk_value: Any) -> None:
        await self.client.delete(spec.table_name, pk_value)

    async def delete_by(self, spec: TableSpec, filters: Dict[str, Any]) -> int:
        if not filters:
            raise ValueError("delete_by requires filters")
        return await self.client.delete_by(spec.table_name, filters)

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        if self.client.in_transaction:
            yield
            return

        transaction_id = None
        try:
            transaction_id = await self.client.begin_transaction()
            yield
            await self.client.commit_transaction()
        except Exception as e:
            if transaction_id:
                await self.client.rollback_transaction()
            raise

    async def close(self):
        await self.client.close()
        self._connected = False
        logger.info("HTTPBackend: Closed connection")

    @property
    def is_connected(self) -> bool:
        return self._connected
