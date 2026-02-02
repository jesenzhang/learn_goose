"""
System Store base interfaces.

This module defines a neutral storage layer for different subsystems
(events, artifacts, session memory) without coupling domain logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from datetime import datetime


class StoreType(str, Enum):
    MEMORY = "memory"
    FILE = "file"
    HYBRID = "hybrid"
    DATABASE = "database"
    REMOTE = "remote"


@dataclass
class StoreRef:
    id: str
    type: str
    text: str
    size: int
    storage_type: StoreType
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)
    path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "size": self.size,
            "storage_type": self.storage_type.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "path": self.path,
        }


@dataclass
class StoreConfig:
    store_type: StoreType = StoreType.MEMORY
    enabled: bool = True
    base_dir: str = "store"
    db_path: str = "store.db"
    memory_threshold: int = 10 * 1024
    file_threshold: int = 100 * 1024
    compression: bool = True
    max_items: int = 50
    max_size_bytes: int = 50 * 1024 * 1024
    ttl: int = 86400
    cleanup_interval: int = 3600
    plugin_path: Optional[str] = None
    plugin_settings: Dict[str, Any] = field(default_factory=dict)


class Store(Protocol):
    config: StoreConfig

    def __init__(self, scope_id: str, config: Optional[StoreConfig] = None, **kwargs) -> None: ...
    async def initialize(self) -> None: ...
    async def store(self, ref: StoreRef, data: Any) -> StoreRef: ...
    async def load(self, ref: StoreRef) -> Optional[Any]: ...
    async def load_lines(self, ref: StoreRef, start: int, limit: int) -> List[str]: ...
    async def search(self, ref: StoreRef, pattern: str, max_hits: int = 20) -> List[str]: ...
    async def delete(self, ref: StoreRef) -> bool: ...
    async def exists(self, ref: StoreRef) -> bool: ...
    async def list_all(self) -> List[StoreRef]: ...
    async def get_stats(self) -> Dict[str, Any]: ...
    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int: ...
    async def cleanup_all(self) -> int: ...
    async def shutdown(self) -> None: ...
