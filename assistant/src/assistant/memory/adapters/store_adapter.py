"""
Adapter to use system store module as memory store backend.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..store import MemoryStore, MemoryRef, StoreType as MemoryStoreType
from ...store.base import Store as SystemStore, StoreConfig, StoreRef, StoreType as SystemStoreType
from ...store.registry import get_registry


def _map_store_type(value: str) -> SystemStoreType:
    try:
        return SystemStoreType(value)
    except Exception:
        return SystemStoreType.MEMORY


def _map_memory_store_type(value: SystemStoreType) -> MemoryStoreType:
    try:
        return MemoryStoreType(value.value)
    except Exception:
        return MemoryStoreType.MEMORY


class StoreModuleAdapter(MemoryStore):
    def __init__(self, session_id: str, config: Optional[StoreConfig] = None, **_kwargs) -> None:
        self.session_id = str(session_id)
        self.config = config or StoreConfig()
        self._store_config = self.config
        self._store: Optional[SystemStore] = None

    async def initialize(self) -> None:
        registry = get_registry()
        self._store = registry.create(self.session_id, self._store_config)
        await self._store.initialize()

    async def store(self, ref: MemoryRef, data: Any) -> MemoryRef:
        store_ref = StoreRef(
            id=ref.id,
            type=ref.type,
            text=ref.text,
            size=ref.size,
            storage_type=_map_store_type(ref.storage_type.value),
            created_at=ref.created_at,
            metadata=ref.metadata,
            path=ref.path,
        )
        stored = await self._store.store(store_ref, data)
        return MemoryRef(
            id=stored.id,
            type=stored.type,
            text=stored.text,
            size=stored.size,
            storage_type=_map_memory_store_type(stored.storage_type),
            created_at=stored.created_at,
            metadata=stored.metadata,
            path=stored.path,
        )

    async def load(self, ref: MemoryRef) -> Optional[Any]:
        store_ref = StoreRef(
            id=ref.id,
            type=ref.type,
            text=ref.text,
            size=ref.size,
            storage_type=_map_store_type(ref.storage_type.value),
            created_at=ref.created_at,
            metadata=ref.metadata,
            path=ref.path,
        )
        return await self._store.load(store_ref)

    async def delete(self, ref: MemoryRef) -> bool:
        store_ref = StoreRef(
            id=ref.id,
            type=ref.type,
            text=ref.text,
            size=ref.size,
            storage_type=_map_store_type(ref.storage_type.value),
            created_at=ref.created_at,
            metadata=ref.metadata,
            path=ref.path,
        )
        return await self._store.delete(store_ref)

    async def exists(self, ref: MemoryRef) -> bool:
        store_ref = StoreRef(
            id=ref.id,
            type=ref.type,
            text=ref.text,
            size=ref.size,
            storage_type=_map_store_type(ref.storage_type.value),
            created_at=ref.created_at,
            metadata=ref.metadata,
            path=ref.path,
        )
        return await self._store.exists(store_ref)

    async def list_all(self) -> List[MemoryRef]:
        refs = await self._store.list_all()
        results = []
        for ref in refs:
            results.append(
                MemoryRef(
                    id=ref.id,
                    type=ref.type,
                    text=ref.text,
                    size=ref.size,
                    storage_type=_map_memory_store_type(ref.storage_type),
                    created_at=ref.created_at,
                    metadata=ref.metadata,
                    path=ref.path,
                )
            )
        return results

    async def get_stats(self) -> Dict[str, Any]:
        return await self._store.get_stats()

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        return await self._store.cleanup_old(older_than_seconds)

    async def cleanup_all(self) -> int:
        return await self._store.cleanup_all()

    async def shutdown(self) -> None:
        if self._store:
            await self._store.shutdown()
            self._store = None


def create_store_module_adapter(session_id: str, config: Optional[StoreConfig] = None) -> StoreModuleAdapter:
    return StoreModuleAdapter(session_id=session_id, config=config)
