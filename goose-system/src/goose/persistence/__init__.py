"""
Persistence Module

Multi-backend persistence layer with schema auto-registration.
Reference: pho persistence implementation.

Supports:
- SQL databases (SQLite, PostgreSQL, MySQL) via SQLAlchemy
- JSONL file storage
- HTTP API backends
"""

from .backend import PersistenceBackend
from .backends import SQLBackend, JSONLBackend, HTTPBackend, parse_db_url
from .backends.http_client import HttpClient, HttpClientConfig, HttpClientError, create_http_client
from .drivers import SQLDriver, SQLiteDriver, SQLAlchemyDriver
from .manager import PersistenceManager, get_persistence, init_persistence, shutdown_persistence
from .repository import BaseRepository, with_table
from .spec import TableSpec, FieldSpec

__all__ = [
    # Backend Interface
    "PersistenceBackend",
    # SQL Backends
    "SQLBackend",
    "SQLDriver",
    "SQLiteDriver",
    "SQLAlchemyDriver",
    # JSONL Backend
    "JSONLBackend",
    # HTTP Backend
    "HTTPBackend",
    "parse_db_url",
    "HttpClient",
    "HttpClientConfig",
    "HttpClientError",
    "create_http_client",
    # Manager
    "PersistenceManager",
    "get_persistence",
    "init_persistence",
    "shutdown_persistence",
    # Repository
    "BaseRepository",
    "with_table",
    # Spec
    "TableSpec",
    "FieldSpec",
]
