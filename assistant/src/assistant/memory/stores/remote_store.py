"""
Remote store implementation (API + WAL).
"""

from __future__ import annotations

import json
import logging
import time
import hmac
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .base import MemoryStore, MemoryStoreConfig, MemoryRef, StoreType

logger = logging.getLogger(__name__)


class RemoteMemoryStore(MemoryStore):
    def __init__(self, session_id: str, config: Optional[MemoryStoreConfig] = None, **kwargs):
        self.session_id = str(session_id)
        self.config = config or MemoryStoreConfig(store_type=StoreType.DATABASE)
        self.base_url = kwargs.get("base_url") or kwargs.get("remote_base_url") or ""
        self.api_key = kwargs.get("api_key") or kwargs.get("remote_api_key")
        self.auth_provider = kwargs.get("auth_provider")
        self.auth_header = kwargs.get("auth_header", "Authorization")
        self.auth_prefix = kwargs.get("auth_prefix", "")
        self.timeout = kwargs.get("timeout", 10.0)
        self.retry_count = int(kwargs.get("retry_count", 3))
        self.retry_backoff = float(kwargs.get("retry_backoff", 0.5))
        self.signature_secret = kwargs.get("signature_secret")
        self.store_path = kwargs.get("store_path", "/memory/store")
        self.load_path = kwargs.get("load_path", "/memory/load")
        self.delete_path = kwargs.get("delete_path", "/memory/delete")
        self.list_path = kwargs.get("list_path", "/memory/list")
        self.stats_path = kwargs.get("stats_path", "/memory/stats")
        self.wal_enabled = bool(kwargs.get("wal_enabled", True))
        self.wal_dir = Path(kwargs.get("wal_dir", "memories_wal")) / self.session_id
        self.wal_path = self.wal_dir / "memory.wal"
        self.wal_ack_path = self.wal_dir / "memory.wal.ack"
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.timeout)
        if self.wal_enabled:
            self.wal_dir.mkdir(parents=True, exist_ok=True)
            await self._replay_wal()

    async def store(self, ref: MemoryRef, data: Any) -> MemoryRef:
        payload = self._serialize(ref, data)
        await self._append_wal("store", payload)
        resp = await self._post(self.store_path, payload)
        if resp is not None:
            ref.size = resp.get("size", ref.size)
        return ref

    async def load(self, ref: MemoryRef) -> Optional[Any]:
        payload = {"session_id": self.session_id, "item_id": ref.id}
        resp = await self._post(self.load_path, payload)
        if not resp:
            return None
        return resp.get("data")

    async def delete(self, ref: MemoryRef) -> bool:
        payload = {
            "session_id": self.session_id,
            "item_id": ref.id,
            "idempotency_key": self._make_idempotency_key(ref.id),
        }
        await self._append_wal("delete", payload)
        resp = await self._post(self.delete_path, payload)
        return bool(resp and resp.get("deleted"))

    async def exists(self, ref: MemoryRef) -> bool:
        payload = {"session_id": self.session_id, "item_id": ref.id}
        resp = await self._post(self.load_path, payload)
        return bool(resp and resp.get("data") is not None)

    async def list_all(self) -> List[MemoryRef]:
        payload = {"session_id": self.session_id}
        resp = await self._post(self.list_path, payload)
        items = []
        for item in resp.get("items", []) if resp else []:
            items.append(
                MemoryRef(
                    id=item.get("id", ""),
                    type=item.get("type", ""),
                    text=item.get("text", ""),
                    size=item.get("size", 0),
                    storage_type=StoreType.DATABASE,
                    created_at=item.get("created_at", datetime.now().timestamp()),
                    metadata=item.get("metadata", {}),
                )
            )
        return items

    async def get_stats(self) -> Dict[str, Any]:
        payload = {"session_id": self.session_id}
        resp = await self._post(self.stats_path, payload)
        return resp or {}

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        # Remote cleanup should be handled by server.
        return 0

    async def cleanup_all(self) -> int:
        # Not implemented; keep minimal.
        return 0

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._client or not self.base_url:
            return None
        url = self.base_url.rstrip("/") + path
        headers = self._build_headers(payload)
        for attempt in range(self.retry_count):
            try:
                resp = await self._client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt >= self.retry_count - 1:
                    logger.warning(f"RemoteMemoryStore request failed: {e}")
                    return None
                await self._sleep_retry(attempt)
        return None

    def _serialize(self, ref: MemoryRef, data: Any) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "item_id": ref.id,
            "type": ref.type,
            "text": ref.text,
            "data": data,
            "metadata": ref.metadata,
            "idempotency_key": self._make_idempotency_key(ref.id),
        }

    async def _append_wal(self, op: str, payload: Dict[str, Any]) -> None:
        if not self.wal_enabled:
            return
        entry = {
            "op": op,
            "ts": datetime.now().timestamp(),
            "payload": payload,
        }
        with open(self.wal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def _replay_wal(self) -> None:
        if not self.wal_path.exists():
            return
        start_offset = self._read_ack_offset()
        try:
            with open(self.wal_path, "rb") as f:
                f.seek(start_offset)
                offset = start_offset
                for line in f:
                    line_len = len(line)
                    if not line.strip():
                        offset += line_len
                        continue
                    try:
                        entry = json.loads(line.decode("utf-8"))
                    except Exception:
                        offset += line_len
                        continue
                    op = entry.get("op")
                    payload = entry.get("payload") or {}
                    if not op or not payload:
                        offset += line_len
                        continue
                    path = self.store_path if op == "store" else self.delete_path
                    resp = await self._post(path, payload)
                    if resp is None:
                        break
                    offset += line_len
                    self._write_ack_offset(offset)
        except Exception as e:
            logger.warning(f"RemoteMemoryStore WAL replay failed: {e}")

    def _read_ack_offset(self) -> int:
        if not self.wal_ack_path.exists():
            return 0
        try:
            return int(self.wal_ack_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            return 0

    def _write_ack_offset(self, offset: int) -> None:
        try:
            self.wal_ack_path.write_text(str(offset), encoding="utf-8")
        except Exception:
            pass

    def _build_headers(self, payload: Dict[str, Any]) -> Dict[str, str]:
        headers = {}
        dynamic_token = self.auth_provider() if callable(self.auth_provider) else None
        if dynamic_token:
            headers[self.auth_header] = f"{self.auth_prefix}{dynamic_token}"
        elif self.api_key:
            headers[self.auth_header] = f"{self.auth_prefix}{self.api_key}"
        key = payload.get("idempotency_key")
        if key:
            headers["Idempotency-Key"] = str(key)
        if self.signature_secret:
            ts = str(int(time.time()))
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            sig = hmac.new(self.signature_secret.encode("utf-8"), (ts + body).encode("utf-8"), hashlib.sha256).hexdigest()
            headers["X-Signature"] = sig
            headers["X-Timestamp"] = ts
        return headers

    def _make_idempotency_key(self, item_id: str) -> str:
        return f"{self.session_id}:{item_id}:{int(time.time() * 1000)}"

    async def _sleep_retry(self, attempt: int) -> None:
        await asyncio.sleep(self.retry_backoff * (attempt + 1))
