"""
System Store manager (neutral storage infrastructure).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

from .base import Store, StoreConfig, StoreRef, StoreType
from .registry import get_registry


@dataclass
class StoreManagerConfig:
    enabled: bool = True
    store_enabled: bool = True
    store_config: Optional[StoreConfig] = None
    store_factory: Optional[Callable[[str], Store]] = None


class StoreManager:
    def __init__(self, config: Optional[StoreManagerConfig] = None):
        self.config = config or StoreManagerConfig()
        self._store_factory = self.config.store_factory
        self._stores: Dict[str, Store] = {}
        if self.config.store_config is None:
            self.config.store_config = StoreConfig()

    def inject_store_factory(self, factory: Callable[[str], Store]) -> None:
        self._store_factory = factory

    def inject_store(self, scope_id: str, store: Store) -> None:
        self._stores[str(scope_id)] = store

    async def _get_store(self, scope_id: str) -> Store:
        sid = str(scope_id)
        if sid in self._stores:
            return self._stores[sid]
        if self._store_factory:
            store = self._store_factory(sid)
        else:
            registry = get_registry()
            cfg = self.config.store_config or StoreConfig()
            store = registry.create(sid, cfg)
        await store.initialize()
        self._stores[sid] = store
        return store

    async def store(
        self,
        *,
        scope_id: str,
        item_id: str,
        item_type: str,
        data: Any,
        text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StoreRef:
        if not self.config.enabled or not self.config.store_enabled:
            raise RuntimeError("Store is disabled")
        store = await self._get_store(scope_id)
        ref = StoreRef(
            id=item_id,
            type=item_type,
            text=text,
            size=0,
            storage_type=StoreType.MEMORY,
            metadata=metadata or {},
        )
        return await store.store(ref, data)

    async def load(self, *, scope_id: str, item_id: str) -> Optional[Any]:
        if not self.config.enabled or not self.config.store_enabled:
            return None
        store = await self._get_store(scope_id)
        ref = StoreRef(
            id=item_id,
            type="",
            text="",
            size=0,
            storage_type=StoreType.MEMORY,
        )
        return await store.load(ref)

    async def delete(self, *, scope_id: str, item_id: str) -> bool:
        if not self.config.enabled or not self.config.store_enabled:
            return False
        store = await self._get_store(scope_id)
        ref = StoreRef(
            id=item_id,
            type="",
            text="",
            size=0,
            storage_type=StoreType.MEMORY,
        )
        return await store.delete(ref)

    async def list_all(self, *, scope_id: str) -> List[StoreRef]:
        if not self.config.enabled or not self.config.store_enabled:
            return []
        store = await self._get_store(scope_id)
        return await store.list_all()

    async def get_stats(self, *, scope_id: str) -> Dict[str, Any]:
        if not self.config.enabled or not self.config.store_enabled:
            return {}
        store = await self._get_store(scope_id)
        return await store.get_stats()

    async def cleanup_scope(self, *, scope_id: str) -> int:
        if not self.config.enabled or not self.config.store_enabled:
            return 0
        store = await self._get_store(scope_id)
        count = await store.cleanup_all()
        self._stores.pop(str(scope_id), None)
        return count

    async def shutdown(self) -> None:
        for store in self._stores.values():
            await store.shutdown()
        self._stores.clear()
