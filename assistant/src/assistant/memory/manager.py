"""
Memory manager - unified memory entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
import inspect

from .store import MemoryStore, MemoryRef, StoreType
from .session_memory import SessionMemoryUpdater
from .llm_adapter import MessageBuilder, LLMCall


@dataclass
class MemoryConfig:
    enabled: bool = True
    store_factory: Optional[Callable[[str], MemoryStore]] = None
    store_profiles: Dict[str, Any] = None
    store_routing: Dict[str, str] = None
    default_store: str = "memory"
    message_builder: Optional[MessageBuilder] = None
    llm_call: Optional[LLMCall] = None


class MemoryManager:
    def __init__(self,config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()
        self._store_factory = self.config.store_factory
        self._stores: Dict[str, MemoryStore] = {}
        self._session_updater: Optional[SessionMemoryUpdater] = None

    def bind_session_updater(self, updater: SessionMemoryUpdater) -> None:
        self._session_updater = updater

    def bind_message_builder(self, message_builder: MessageBuilder) -> None:
        self.config.message_builder = message_builder
        if self._session_updater:
            self._session_updater._message_builder = message_builder

    def bind_llm_call(self, llm_call: LLMCall) -> None:
        self.config.llm_call = llm_call
        if self._session_updater:
            self._session_updater._llm_call = llm_call

    def build_session_updater(self) -> SessionMemoryUpdater:
        updater = SessionMemoryUpdater(
            self.config,
            message_builder=self.config.message_builder,
            llm_call=self.config.llm_call,
        )
        self._session_updater = updater
        return updater

    def inject_store_factory(self, factory: Callable[[str], MemoryStore]) -> None:
        self._store_factory = factory

    def inject_store(self, session_id: str | int, store: MemoryStore) -> None:
        self._stores[str(session_id)] = store

    def inject_store_for_key(self, session_id: str | int, store_key: str, store: MemoryStore) -> None:
        self._stores[f"{str(session_id)}:{store_key}"] = store

    async def _get_store(self, session_id: str | int) -> MemoryStore:
        sid = str(session_id)
        if sid in self._stores:
            return self._stores[sid]
        if self._store_factory:
            store = self._store_factory(sid)
        else:
            store = self._build_store(sid)
        await store.initialize()
        self._stores[sid] = store
        return store

    def _build_store(self, session_id: str) -> MemoryStore:
        return self._build_store_for_key(session_id, self.config.default_store)

    def _build_store_for_key(self, session_id: str, store_key: str) -> MemoryStore:
        from .adapters.store_adapter import create_store_module_adapter

        profiles = self.config.store_profiles or {}
        cfg = profiles.get(store_key)
        return create_store_module_adapter(session_id, cfg)

    def _resolve_store_key(self, *, item_type: Optional[str], storage_type: StoreType | str | None) -> str:
        if isinstance(storage_type, StoreType):
            return storage_type.value
        if isinstance(storage_type, str) and storage_type:
            return storage_type
        routing = self.config.store_routing or {}
        if item_type and item_type in routing:
            return routing[item_type]
        return self.config.default_store

    async def _get_store_for_key(self, session_id: str | int, store_key: str) -> MemoryStore:
        sid = str(session_id)
        cache_key = f"{sid}:{store_key}"
        if cache_key in self._stores:
            return self._stores[cache_key]
        if self._store_factory:
            try:
                params = list(inspect.signature(self._store_factory).parameters.keys())
            except Exception:
                params = []
            if len(params) >= 2:
                store = self._store_factory(sid, (self.config.store_profiles or {}).get(store_key))
            else:
                store = self._store_factory(sid)
        else:
            store = self._build_store_for_key(sid, store_key)
        await store.initialize()
        self._stores[cache_key] = store
        return store

    @staticmethod
    def _coerce_store_type(value: Any) -> StoreType:
        if isinstance(value, StoreType):
            return value
        if isinstance(value, str):
            try:
                return StoreType(value)
            except Exception:
                return StoreType.MEMORY
        return StoreType.MEMORY

    # --- Store Facade ---
    async def store(
        self,
        *,
        session_id: str | int,
        item_id: str,
        item_type: str,
        data: Any,
        text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        storage_type: StoreType | str | None = None,
    ):
        if not self.config.enabled:
            raise RuntimeError("Memory store not available")
        store_key = self._resolve_store_key(item_type=item_type, storage_type=storage_type)
        store = await self._get_store_for_key(session_id, store_key)
        ref = MemoryRef(
            id=item_id,
            type=item_type,
            text=text,
            size=0,
            storage_type=self._coerce_store_type(storage_type),
            metadata=metadata or {},
        )
        return await store.store(ref, data)

    async def load(
        self,
        *,
        session_id: str | int,
        item_id: str,
        storage_type: StoreType | str | None = None,
    ) -> Optional[Any]:
        if not self.config.enabled:
            return None
        store_key = self._resolve_store_key(item_type=None, storage_type=storage_type)
        store = await self._get_store_for_key(session_id, store_key)
        ref = MemoryRef(
            id=item_id,
            type="",
            text="",
            size=0,
            storage_type=StoreType.MEMORY,
        )
        return await store.load(ref)

    async def delete(
        self,
        *,
        session_id: str | int,
        item_id: str,
        storage_type: StoreType | str | None = None,
    ) -> bool:
        if not self.config.enabled:
            return False
        store_key = self._resolve_store_key(item_type=None, storage_type=storage_type)
        store = await self._get_store_for_key(session_id, store_key)
        ref = MemoryRef(
            id=item_id,
            type="",
            text="",
            size=0,
            storage_type=StoreType.MEMORY,
        )
        return await store.delete(ref)

    async def list_all(
        self,
        *,
        session_id: str | int,
        storage_type: StoreType | str | None = None,
    ) -> List[Any]:
        if not self.config.enabled:
            return []
        store_key = self._resolve_store_key(item_type=None, storage_type=storage_type)
        store = await self._get_store_for_key(session_id, store_key)
        return await store.list_all()

    async def get_stats(
        self,
        *,
        session_id: str | int,
        storage_type: StoreType | str | None = None,
    ) -> Dict[str, Any]:
        if not self.config.enabled:
            return {}
        store_key = self._resolve_store_key(item_type=None, storage_type=storage_type)
        store = await self._get_store_for_key(session_id, store_key)
        return await store.get_stats()

    async def cleanup_session(self, *, session_id: str | int) -> int:
        if not self.config.enabled:
            return 0
        store = await self._get_store(session_id)
        count = await store.cleanup_all()
        self._stores.pop(str(session_id), None)
        return count

    async def shutdown(self) -> None:
        for store in self._stores.values():
            await store.shutdown()
        self._stores.clear()


_global_manager: Optional[MemoryManager] = None


def init_manager(
    config: Optional[MemoryConfig] = None,
    message_builder: Optional[MessageBuilder] = None,
    llm_call: Optional[LLMCall] = None,
) -> MemoryManager:
    global _global_manager
    if _global_manager is None:
        if config is None:
            config = MemoryConfig()
        if message_builder is not None:
            config.message_builder = message_builder
        if llm_call is not None:
            config.llm_call = llm_call
        _global_manager = MemoryManager(config=config)
    return _global_manager


def get_manager() -> Optional[MemoryManager]:
    return _global_manager
