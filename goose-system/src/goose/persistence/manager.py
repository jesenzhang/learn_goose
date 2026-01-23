"""
Persistence Manager

Central manager for persistence backends.
Reference: pho persistence manager implementation.
"""

import logging
from typing import Optional
from .backend import PersistenceBackend
from .repository import BaseRepository

logger = logging.getLogger("goose.persistence")


class PersistenceManager:
    """
    Persistence layer manager.

    Responsibilities:
    1. Parse db_url and instantiate appropriate backend
    2. Manage backend lifecycle (boot/shutdown)
    3. Coordinate schema registration and initialization
    """

    def __init__(self, db_url: str = "file://./data"):
        """
        Initialize persistence manager.

        Args:
            db_url: Connection string
                - file://./data - JSONL files
                - sqlite:///goose.db - SQLite
                - postgresql://user:pass@host/db - PostgreSQL
                - http://localhost:8000 - HTTP API
                - http://localhost:8000?api_key=xxx - HTTP API with auth
        """
        self.db_url = db_url
        self._backend: Optional[PersistenceBackend] = None

    @property
    def backend(self) -> PersistenceBackend:
        """Lazy load the backend."""
        if self._backend is None:
            self._backend = self._create_backend()
        return self._backend

    def _create_backend(self) -> PersistenceBackend:
        """Create backend based on URL scheme."""
        uri = self.db_url

        if uri.startswith("http://") or uri.startswith("https://"):
            from .backends.http_backend import HTTPBackend, parse_db_url
            base_url, api_key, config_kwargs = parse_db_url(uri)
            logger.info(f"Using HTTP Backend (url={base_url})")
            return HTTPBackend(base_url=base_url, api_key=api_key, **config_kwargs)

        elif uri.startswith("file://") or uri.endswith(".jsonl"):
            from .backends.jsonl_backend import JsonlBackend
            path = uri.replace("file://", "") or "./data"
            logger.info(f"Using JSONL Backend (path={path})")
            return JsonlBackend(data_dir=path)

        elif "://" in uri:
            from .backends.sql_backend import SQLBackend
            logger.info(f"Using SQL Backend (url={uri})")
            return SQLBackend(db_url=uri)

        else:
            from .backends.jsonl_backend import JsonlBackend
            logger.warning(f"Unknown scheme in '{uri}', falling back to JSONL.")
            return JsonlBackend(data_dir="./data")

    async def boot(self) -> None:
        """Initialize persistence layer."""
        logger.info("Booting persistence layer...")
        schemas = BaseRepository.get_all_schemas()
        if not schemas:
            logger.warning("No schemas found. Did you import your repositories?")
        await self.backend.boot(schemas)
        logger.info(f"Booted with {len(schemas)} tables.")

    async def shutdown(self) -> None:
        """Shutdown persistence layer."""
        if self._backend:
            if hasattr(self._backend, 'close'):
                await self._backend.close()
            logger.info("Persistence shutdown complete.")

    def transaction(self):
        """Get transaction context."""
        return self.backend.transaction()


_GLOBAL_PM: Optional[PersistenceManager] = None


def init_persistence(db_url: str) -> PersistenceManager:
    """Initialize global persistence manager."""
    global _GLOBAL_PM
    if _GLOBAL_PM is not None:
        logger.warning("PersistenceManager already initialized!")
        return _GLOBAL_PM
    logger.info(f"Initializing PersistenceManager with {db_url}")
    _GLOBAL_PM = PersistenceManager(db_url)
    return _GLOBAL_PM


def get_persistence() -> PersistenceManager:
    """Get global persistence manager."""
    if _GLOBAL_PM is None:
        raise RuntimeError(
            "PersistenceManager not initialized. "
            "Call 'init_persistence(db_url)' first."
        )
    return _GLOBAL_PM


async def shutdown_persistence() -> None:
    """Shutdown global persistence manager."""
    global _GLOBAL_PM
    if _GLOBAL_PM:
        await _GLOBAL_PM.shutdown()
        _GLOBAL_PM = None
