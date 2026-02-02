"""
SQLite store implementation.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..base import Store, StoreConfig, StoreRef, StoreType
from ..registry import register_store


@register_store(StoreType.DATABASE)
class SQLiteMemoryStore(Store):
    def __init__(self, session_id: str, config: Optional[StoreConfig] = None, **_kwargs):
        self.session_id = str(session_id)
        self.config = config or StoreConfig(store_type=StoreType.DATABASE)
        self._conn: Optional[sqlite3.Connection] = None

    async def initialize(self) -> None:
        self._conn = sqlite3.connect(self.config.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                session_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_type TEXT,
                item_text TEXT,
                item_size INTEGER,
                data_json TEXT,
                created_at REAL,
                metadata TEXT,
                PRIMARY KEY (session_id, item_id)
            )
            """
        )
        self._conn.commit()

    async def store(self, ref: StoreRef, data: Any) -> StoreRef:
        payload = json.dumps(data, ensure_ascii=False)
        size = len(payload.encode("utf-8"))
        ref.size = size
        ref.storage_type = StoreType.DATABASE
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memory_items
            (session_id, item_id, item_type, item_text, item_size, data_json, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.session_id,
                ref.id,
                ref.type,
                ref.text,
                ref.size,
                payload,
                ref.created_at,
                json.dumps(ref.metadata, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return ref

    async def load(self, ref: StoreRef) -> Optional[Any]:
        cur = self._conn.execute(
            "SELECT data_json FROM memory_items WHERE session_id = ? AND item_id = ?",
            (self.session_id, ref.id),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    async def load_lines(self, ref: StoreRef, start: int, limit: int) -> List[str]:
        data = await self.load(ref)
        if data is None:
            return []
        if isinstance(data, str):
            lines = data.splitlines()
        else:
            lines = json.dumps(data, ensure_ascii=False).splitlines()
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
            lines = json.dumps(data, ensure_ascii=False).splitlines()
        hits = []
        for line in lines:
            if pattern in line:
                hits.append(line)
                if len(hits) >= max_hits:
                    break
        return hits

    async def delete(self, ref: StoreRef) -> bool:
        cur = self._conn.execute(
            "DELETE FROM memory_items WHERE session_id = ? AND item_id = ?",
            (self.session_id, ref.id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    async def exists(self, ref: StoreRef) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM memory_items WHERE session_id = ? AND item_id = ? LIMIT 1",
            (self.session_id, ref.id),
        )
        return cur.fetchone() is not None

    async def list_all(self) -> List[StoreRef]:
        cur = self._conn.execute(
            """
            SELECT item_id, item_type, item_text, item_size, created_at, metadata
            FROM memory_items WHERE session_id = ? ORDER BY created_at DESC
            """,
            (self.session_id,),
        )
        items = []
        for row in cur.fetchall():
            metadata = {}
            if row[5]:
                try:
                    metadata = json.loads(row[5])
                except Exception:
                    metadata = {}
            items.append(
                StoreRef(
                    id=row[0],
                    type=row[1] or "",
                    text=row[2] or "",
                    size=row[3] or 0,
                    storage_type=StoreType.DATABASE,
                    created_at=row[4] or datetime.now().timestamp(),
                    metadata=metadata,
                )
            )
        return items

    async def get_stats(self) -> Dict[str, Any]:
        cur = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(item_size), 0) FROM memory_items WHERE session_id = ?",
            (self.session_id,),
        )
        row = cur.fetchone() or (0, 0)
        return {"total_count": row[0], "total_size": row[1], "db_path": self.config.db_path}

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        ttl = older_than_seconds or self.config.ttl
        threshold = datetime.now().timestamp() - ttl
        cur = self._conn.execute(
            "DELETE FROM memory_items WHERE session_id = ? AND created_at < ?",
            (self.session_id, threshold),
        )
        self._conn.commit()
        return cur.rowcount or 0

    async def cleanup_all(self) -> int:
        cur = self._conn.execute(
            "DELETE FROM memory_items WHERE session_id = ?",
            (self.session_id,),
        )
        self._conn.commit()
        return cur.rowcount or 0

    async def shutdown(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
