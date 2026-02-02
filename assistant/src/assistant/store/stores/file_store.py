"""
Local file store implementation.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Store, StoreConfig, StoreRef, StoreType
from ..registry import register_store

logger = logging.getLogger(__name__)


@register_store(StoreType.FILE)
class FileMemoryStore(Store):
    def __init__(self, session_id: str, config: Optional[StoreConfig] = None, **_kwargs):
        self.session_id = str(session_id)
        self.config = config or StoreConfig(store_type=StoreType.FILE)
        self._index: Dict[str, StoreRef] = {}
        self._base_dir = Path(self.config.base_dir) / self.session_id
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        return None

    async def store(self, ref: StoreRef, data: Any) -> StoreRef:
        content_type = (ref.metadata or {}).get("content_type")
        if content_type == "markdown" and isinstance(data, str):
            payload = data
            ext = ".md"
        else:
            payload = json.dumps(data, ensure_ascii=False)
            ext = ".json"
        size = len(payload.encode("utf-8"))
        ref.size = size
        ref.storage_type = StoreType.FILE
        ref.path = str(self._get_file_path(ref.id, ext))
        with open(ref.path, "w", encoding="utf-8") as f:
            f.write(payload)
        self._index[ref.id] = ref
        self._maybe_cleanup()
        return ref

    async def load(self, ref: StoreRef) -> Optional[Any]:
        stored = self._index.get(ref.id)
        if not stored or not stored.path:
            return None
        try:
            with open(stored.path, "r", encoding="utf-8") as f:
                content = f.read()
            if stored.path.endswith(".md"):
                return content
            return json.loads(content)
        except FileNotFoundError:
            return None

    async def delete(self, ref: StoreRef) -> bool:
        stored = self._index.get(ref.id)
        if not stored:
            return False
        if stored.path:
            try:
                os.remove(stored.path)
            except FileNotFoundError:
                pass
        self._index.pop(ref.id, None)
        return True

    async def exists(self, ref: StoreRef) -> bool:
        return ref.id in self._index

    async def list_all(self) -> List[StoreRef]:
        return list(self._index.values())

    async def load_lines(self, ref: StoreRef, start: int, limit: int) -> List[str]:
        stored = self._index.get(ref.id)
        if not stored or not stored.path:
            return []
        if start < 0:
            start = 0
        if limit <= 0:
            return []
        lines = []
        try:
            with open(stored.path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    if idx < start:
                        continue
                    lines.append(line.rstrip("\n"))
                    if len(lines) >= limit:
                        break
        except FileNotFoundError:
            return []
        return lines

    async def search(self, ref: StoreRef, pattern: str, max_hits: int = 20) -> List[str]:
        stored = self._index.get(ref.id)
        if not stored or not stored.path or not pattern:
            return []
        hits: List[str] = []
        try:
            with open(stored.path, "r", encoding="utf-8") as f:
                for line in f:
                    if pattern in line:
                        hits.append(line.rstrip("\n"))
                        if len(hits) >= max_hits:
                            break
        except FileNotFoundError:
            return []
        return hits

    async def get_stats(self) -> Dict[str, Any]:
        total_size = sum(r.size for r in self._index.values())
        return {
            "total_count": len(self._index),
            "total_size": total_size,
            "base_dir": str(self._base_dir),
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
        if self._base_dir.exists():
            shutil.rmtree(self._base_dir, ignore_errors=True)
        return count

    async def shutdown(self) -> None:
        return None

    def _get_file_path(self, rid: str, ext: str) -> Path:
        return self._base_dir / f"mem_{rid}{ext}"

    def _maybe_cleanup(self) -> None:
        total_items = len(self._index)
        total_size = sum(r.size for r in self._index.values())
        if total_items <= self.config.max_items and total_size <= self.config.max_size_bytes:
            return
        ordered = sorted(self._index.items(), key=lambda item: item[1].created_at)
        to_remove = max(1, int(len(ordered) * 0.2))
        for rid, ref in ordered[:to_remove]:
            if ref.path:
                try:
                    os.remove(ref.path)
                except FileNotFoundError:
                    pass
            self._index.pop(rid, None)
