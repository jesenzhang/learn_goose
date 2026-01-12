"""
HTTP Backend for Persistence Layer

This module provides a backend implementation that communicates with a unified
HTTP API for database operations. Useful for scenarios where database access
needs to go through a centralized service.
"""

import logging
from typing import Any, Dict, List, Optional, AsyncGenerator
from contextlib import asynccontextmanager

from ..backend import PersistenceBackend
from ..spec import TableSpec
from .http_client import HttpClient, HttpClientError, create_http_client, HttpClientConfig


logger = logging.getLogger(__name__)


class HTTPBackend(PersistenceBackend):
    """
    [Adapter] HTTP API Backend for persistence operations

    Communicates with a unified HTTP API service for database operations.
    This is useful when:
    - Database access needs to go through a centralized service
    - You need to delegate database operations to another service
    - You want to abstract database implementation details
    - You need unified logging/auditing of all database operations

    Example:
        backend = HTTPBackend(
            base_url="https://api.example.com",
            api_key="your-api-key"
        )
        await backend.boot(schemas)
        await backend.insert(spec, {"id": "1", "name": "test"})
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        **config_kwargs
    ):
        """
        Initialize HTTP Backend

        Args:
            base_url: Base URL of the API service (e.g., "https://api.example.com")
            api_key: Optional API key for authentication
            **config_kwargs: Additional HttpClientConfig options:
                - api_key_header: Header name for API key (default: "X-API-Key")
                - timeout: Request timeout in seconds (default: 30.0)
                - max_retries: Maximum number of retries (default: 3)
                - retry_delay: Delay between retries in seconds (default: 0.5)
                - headers: Additional headers to include
                - verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.config = HttpClientConfig(
            base_url=base_url,
            api_key=api_key,
            **config_kwargs
        )
        self.client = create_http_client(base_url, api_key, **config_kwargs)
        self._connected = False

    async def boot(self, schemas: List[Dict]):
        """
        Initialize the HTTP backend by sending schemas to the API

        Args:
            schemas: List of schema dictionaries containing:
                - table_name: Name of the table
                - schema_sql: SQL statement(s) to create the table
                - pk_field: Primary key field name
                - priority: Table creation priority
        """
        if self._connected:
            logger.warning("HTTPBackend already booted")
            return

        try:
            # Transform schemas to API format
            api_schemas = []
            for s in schemas:
                # Handle both dict and TableSpec objects
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

            response = await self.client.boot(api_schemas)
            self._connected = True
            logger.info(f"HTTPBackend: Booted successfully with {len(schemas)} tables")

            # Return response for potential debugging
            return response

        except HttpClientError as e:
            logger.error(f"HTTPBackend boot failed: {e}")
            raise

    async def insert(self, spec: TableSpec, data: Dict[str, Any]) -> Dict:
        """Insert a new record"""
        try:
            response = await self.client.insert(spec.table_name, data)
            logger.debug(f"Inserted into {spec.table_name}: {data.get(spec.pk_field)}")
            return response
        except HttpClientError as e:
            logger.error(f"Insert failed for {spec.table_name}: {e}")
            raise

    async def get(self, spec: TableSpec, pk_value: Any) -> Optional[Dict]:
        """Get a record by primary key"""
        try:
            result = await self.client.get(spec.table_name, pk_value)
            logger.debug(f"Retrieved from {spec.table_name}: {pk_value}")
            return result
        except HttpClientError as e:
            if e.status_code == 404:
                return None
            logger.error(f"Get failed for {spec.table_name}/{pk_value}: {e}")
            raise

    async def get_batch(self, spec: TableSpec, pk_values: List[Any]) -> List[Dict]:
        """Get multiple records by primary keys"""
        if not pk_values:
            return []

        try:
            results = await self.client.get_batch(spec.table_name, pk_values)
            logger.debug(f"Retrieved {len(results)} records from {spec.table_name}")
            return results
        except HttpClientError as e:
            logger.error(f"Get batch failed for {spec.table_name}: {e}")
            raise

    async def find(
        self,
        spec: TableSpec,
        filters: Dict[str, Any],
        limit: int = -1,
        offset: int = 0
    ) -> List[Dict]:
        """Find records matching filters"""
        try:
            results = await self.client.find(spec.table_name, filters, limit, offset)
            logger.debug(f"Found {len(results)} records in {spec.table_name}")
            return results
        except HttpClientError as e:
            logger.error(f"Find failed for {spec.table_name}: {e}")
            raise

    async def count(self, spec: TableSpec, filters: Dict[str, Any]) -> int:
        """Count records matching filters"""
        try:
            count = await self.client.count(spec.table_name, filters)
            logger.debug(f"Counted {count} records in {spec.table_name}")
            return count
        except HttpClientError as e:
            logger.error(f"Count failed for {spec.table_name}: {e}")
            raise

    async def update(self, spec: TableSpec, pk_value: Any, data: Dict[str, Any]) -> Dict:
        """Update a record by primary key"""
        try:
            response = await self.client.update(spec.table_name, pk_value, data)
            logger.debug(f"Updated {spec.table_name}/{pk_value}")
            return response
        except HttpClientError as e:
            logger.error(f"Update failed for {spec.table_name}/{pk_value}: {e}")
            raise

    async def update_by(
        self,
        spec: TableSpec,
        filters: Dict[str, Any],
        data: Dict[str, Any]
    ) -> int:
        """Update records matching filters"""
        if not filters:
            raise ValueError("update_by requires filters")

        try:
            affected_rows = await self.client.update_by(spec.table_name, filters, data)
            logger.debug(f"Updated {affected_rows} records in {spec.table_name}")
            return affected_rows
        except HttpClientError as e:
            logger.error(f"Update by failed for {spec.table_name}: {e}")
            raise

    async def upsert(self, spec: TableSpec, data: Dict[str, Any]) -> Dict:
        """Insert or update a record"""
        try:
            response = await self.client.upsert(spec.table_name, data)
            logger.debug(f"Upserted {spec.table_name}/{data.get(spec.pk_field)}")
            return response
        except HttpClientError as e:
            logger.error(f"Upsert failed for {spec.table_name}: {e}")
            raise

    async def delete(self, spec: TableSpec, pk_value: Any) -> Dict:
        """Delete a record by primary key"""
        try:
            response = await self.client.delete(spec.table_name, pk_value)
            logger.debug(f"Deleted {spec.table_name}/{pk_value}")
            return response
        except HttpClientError as e:
            logger.error(f"Delete failed for {spec.table_name}/{pk_value}: {e}")
            raise

    async def delete_by(self, spec: TableSpec, filters: Dict[str, Any]) -> int:
        """Delete records matching filters"""
        if not filters:
            raise ValueError("delete_by requires filters")

        try:
            affected_rows = await self.client.delete_by(spec.table_name, filters)
            logger.debug(f"Deleted {affected_rows} records from {spec.table_name}")
            return affected_rows
        except HttpClientError as e:
            logger.error(f"Delete by failed for {spec.table_name}: {e}")
            raise

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """
        Transaction context manager

        Note: The actual transaction is managed on the server side.
        The client just wraps operations in a transaction ID.
        """
        if self.client.in_transaction:
            # Already in a transaction (nested), just yield
            logger.debug("Already in transaction, nesting")
            yield
            return

        transaction_id = None
        try:
            transaction_id = await self.client.begin_transaction()
            logger.debug(f"Transaction started: {transaction_id}")
            yield
            await self.client.commit_transaction()
            logger.debug(f"Transaction committed: {transaction_id}")
        except Exception as e:
            if transaction_id:
                await self.client.rollback_transaction()
                logger.debug(f"Transaction rolled back: {transaction_id}")
            raise

    async def close(self):
        """Close the HTTP client connection"""
        await self.client.close()
        self._connected = False
        logger.info("HTTPBackend: Closed connection")

    @property
    def is_connected(self) -> bool:
        """Check if backend is connected"""
        return self._connected


def parse_db_url(db_url: str) -> tuple[str, Optional[str], dict]:
    """
    Parse database URL for HTTP backend

    Supported formats:
    - http://localhost:8000
    - https://api.example.com
    - http://localhost:8000?api_key=xxx
    - http://localhost:8000?api_key=xxx&timeout=60

    Returns:
        tuple of (base_url, api_key, config_kwargs)
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(db_url)

    # Extract base URL (without query string)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Parse query parameters
    query_params = parse_qs(parsed.query)

    # Extract api_key
    api_key = None
    if "api_key" in query_params:
        api_key = query_params["api_key"][0]

    # Extract other config options
    config_kwargs = {}
    for key, values in query_params.items():
        if key == "api_key":
            continue
        value = values[0]

        # Convert typed parameters
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
