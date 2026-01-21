"""
Persistence Module

Multi-backend persistence layer with schema auto-registration.
Reference: pho persistence implementation.

Supports:
- SQL databases (SQLite, PostgreSQL, MySQL)
- JSONL file storage
- HTTP API backends
"""

from .backend import PersistenceBackend
from .backends import SQLBackend, JSONLBackend
from .manager import PersistenceManager, get_persistence, init_persistence, shutdown_persistence
from .repository import BaseRepository, with_table
from .spec import TableSpec, FieldSpec

__all__ = [
    "PersistenceBackend",
    "SQLBackend",
    "JSONLBackend",
    "PersistenceManager",
    "BaseRepository",
    "with_table",
    "TableSpec",
    "FieldSpec",
    "get_persistence",
    "init_persistence",
    "shutdown_persistence",
]
