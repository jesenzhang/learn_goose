"""
Persistence Backend Interface

Abstract interface for persistence backends.
Reference: pho persistence backend implementation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncGenerator
from contextlib import asynccontextmanager


class PersistenceBackend(ABC):
    """
    Abstract interface for persistence backends.

    Supports:
    - CRUD operations
    - Batch operations
    - Filter-based queries
    - Transactions
    """

    @abstractmethod
    async def boot(self, schemas: List[Dict]) -> None:
        """Initialize backend with schemas."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close backend connections."""
        pass

    @abstractmethod
    async def insert(self, table: str, data: Dict[str, Any]) -> None:
        """Insert a new record."""
        pass

    @abstractmethod
    async def get(self, table: str, pk_value: Any) -> Optional[Dict]:
        """Get a record by primary key."""
        pass

    @abstractmethod
    async def update(self, table: str, pk_value: Any, data: Dict[str, Any]) -> None:
        """Update a record by primary key."""
        pass

    @abstractmethod
    async def upsert(self, table: str, data: Dict[str, Any]) -> None:
        """Insert or update a record."""
        pass

    @abstractmethod
    async def delete(self, table: str, pk_value: Any) -> None:
        """Delete a record by primary key."""
        pass

    @abstractmethod
    async def get_batch(self, table: str, pk_values: List[Any]) -> List[Dict]:
        """Batch get records by primary keys."""
        pass

    @abstractmethod
    async def find(
        self,
        table: str,
        filters: Dict[str, Any],
        limit: int = -1,
        offset: int = 0
    ) -> List[Dict]:
        """Find records by filters."""
        pass

    @abstractmethod
    async def count(self, table: str, filters: Dict[str, Any]) -> int:
        """Count records by filters."""
        pass

    @abstractmethod
    async def update_by(
        self,
        table: str,
        filters: Dict[str, Any],
        data: Dict[str, Any]
    ) -> int:
        """Update records by filters."""
        pass

    @abstractmethod
    async def delete_by(self, table: str, filters: Dict[str, Any]) -> int:
        """Delete records by filters."""
        pass

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """Context manager for transactions."""
        yield
