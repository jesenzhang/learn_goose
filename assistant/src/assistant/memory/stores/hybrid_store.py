"""
Hybrid store implementation (memory + file).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import MemoryStore, MemoryStoreConfig, MemoryRef, StoreType
from .memory_store import MemoryOnlyStore
from .file_store import FileMemoryStore
from .registry import register_store


@register_store(StoreType.HYBRID)
class HybridMemoryStore(MemoryStore):
    def __init__(self, session_id: str, config: Optional[MemoryStoreConfig] = None, **_kwargs):
        self.session_id = str(session_id)
        self.config = config or MemoryStoreConfig(store_type=StoreType.HYBRID)
        self._memory = MemoryOnlyStore(self.session_id, self.config)
        self._file = FileMemoryStore(self.session_id, self.config)

    async def initialize(self) -> None:
        await self._memory.initialize()
        await self._file.initialize()

    async def store(self, ref: MemoryRef, data: Any) -> MemoryRef:
        payload_size = ref.size
        if payload_size <= 0:
            payload_size = len(str(data).encode("utf-8"))
        if payload_size <= self.config.file_threshold:
            return await self._memory.store(ref, data)
        return await self._file.store(ref, data)

    async def load(self, ref: MemoryRef) -> Optional[Any]:
        data = await self._memory.load(ref)
        if data is not None:
            return data
        return await self._file.load(ref)

    async def delete(self, ref: MemoryRef) -> bool:
        deleted = await self._memory.delete(ref)
        deleted = await self._file.delete(ref) or deleted
        return deleted

    async def exists(self, ref: MemoryRef) -> bool:
        if await self._memory.exists(ref):
            return True
        return await self._file.exists(ref)

    async def list_all(self) -> List[MemoryRef]:
        items = await self._memory.list_all()
        items.extend(await self._file.list_all())
        return items

    async def get_stats(self) -> Dict[str, Any]:
        mem_stats = await self._memory.get_stats()
        file_stats = await self._file.get_stats()
        return {
            "memory": mem_stats,
            "file": file_stats,
        }

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        count = await self._memory.cleanup_old(older_than_seconds)
        count += await self._file.cleanup_old(older_than_seconds)
        return count

    async def cleanup_all(self) -> int:
        count = await self._memory.cleanup_all()
        count += await self._file.cleanup_all()
        return count

    async def shutdown(self) -> None:
        await self._memory.shutdown()
        await self._file.shutdown()
