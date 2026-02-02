"""
In-memory store implementation.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..base import Store, StoreConfig, StoreRef, StoreType
from ..registry import register_store

logger = logging.getLogger(__name__)


@register_store(StoreType.MEMORY)
class MemoryOnlyStore(Store):
    def __init__(self, session_id: str, config: Optional[StoreConfig] = None, **_kwargs):
        self.session_id = str(session_id)
        self.config = config or StoreConfig(store_type=StoreType.MEMORY)
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._index: Dict[str, StoreRef] = {}

    async def initialize(self) -> None:
        return None

    async def store(self, ref: StoreRef, data: Any) -> StoreRef:
        payload = json.dumps(data, ensure_ascii=False)
        size = len(payload.encode("utf-8"))
        ref.size = size
        ref.storage_type = StoreType.MEMORY
        if size > self.config.memory_threshold and self.config.compression:
            compressed = gzip.compress(payload.encode("utf-8"))
            self._cache[ref.id] = (compressed, datetime.now().timestamp())
            ref.metadata["compressed"] = True
        else:
            self._cache[ref.id] = (data, datetime.now().timestamp())
        self._index[ref.id] = ref
        self._maybe_cleanup()
        return ref

    async def load(self, ref: StoreRef) -> Optional[Any]:
        stored = self._index.get(ref.id)
        if not stored:
            return None
        if stored.id in self._cache:
            data, _ = self._cache[stored.id]
            self._cache[stored.id] = (data, datetime.now().timestamp())
            if stored.metadata.get("compressed") and isinstance(data, (bytes, bytearray)):
                return json.loads(gzip.decompress(data).decode("utf-8"))
            return data
        return None

    async def load_lines(self, ref: StoreRef, start: int, limit: int) -> List[str]:
        data = await self.load(ref)
        if data is None:
            return []
        if isinstance(data, str):
            lines = data.splitlines()
        else:
            try:
                lines = json.dumps(data, ensure_ascii=False).splitlines()
            except Exception:
                return []
        if start < 0:
            start = 0
        if limit <= 0:
            return []
        return lines[start:start + limit]

    async def search(self, ref: StoreRef, pattern: str, max_hits: int = 20) -> List[str]:
        data = await self.load(ref)
        if data is None or not pattern:
            return []
        if isinstance(data, str):
            lines = data.splitlines()
        else:
            try:
                lines = json.dumps(data, ensure_ascii=False).splitlines()
            except Exception:
                return []
        hits = []
        for line in lines:
            if pattern in line:
                hits.append(line)
                if len(hits) >= max_hits:
                    break
        return hits

    async def delete(self, ref: StoreRef) -> bool:
        if ref.id not in self._index:
            return False
        self._cache.pop(ref.id, None)
        self._index.pop(ref.id, None)
        return True

    async def exists(self, ref: StoreRef) -> bool:
        return ref.id in self._index

    async def list_all(self) -> List[StoreRef]:
        return list(self._index.values())

    async def get_stats(self) -> Dict[str, Any]:
        total_size = sum(r.size for r in self._index.values())
        return {
            "total_count": len(self._index),
            "total_size": total_size,
            "cache_items": len(self._cache),
        }

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        ttl = older_than_seconds or self.config.ttl
        now = datetime.now().timestamp()
        to_delete = [rid for rid, ref in self._index.items() if (now - ref.created_at) > ttl]
        for rid in to_delete:
            await self.delete(self._index[rid])
        return len(to_delete)

    async def cleanup_all(self) -> int:
        count = len(self._index)
        self._index.clear()
        self._cache.clear()
        return count

    async def shutdown(self) -> None:
        self._cache.clear()
        self._index.clear()

    def _maybe_cleanup(self) -> None:
        total_items = len(self._index)
        total_size = sum(r.size for r in self._index.values())
        if total_items <= self.config.max_items and total_size <= self.config.max_size_bytes:
            return
        ordered = sorted(self._index.items(), key=lambda item: item[1].created_at)
        to_remove = max(1, int(len(ordered) * 0.2))
        for rid, _ref in ordered[:to_remove]:
            self._cache.pop(rid, None)
            self._index.pop(rid, None)
