"""
Event Store - 适配 AsyncDatabaseManager 到 IEventStore 接口。
"""
import logging
from typing import List, TypeVar, Optional, Dict, Any
from abc import ABC, abstractmethod
from pydantic import BaseModel
import os
import json
import asyncio
from datetime import datetime
from .types import Event
import hashlib
import time
import uuid
import re
from .legacy import EventType

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=BaseModel)


class IEventStore(ABC):
    """[存储层接口]"""
    @abstractmethod
    async def save_event(self, event: E) -> None:
        pass

    @abstractmethod
    async def get_events(self, session_id: int, run_id: str, after_seq_id: int = -1) -> List[E]:
        pass


class AsyncEventStore(IEventStore):
    """
    使用 AsyncDatabaseManager 的事件存储实现。

    将 pho 的 Event 模型适配到现有的数据库结构。
    """

    def __init__(
        self,
        db_manager,
        storage_dir: str = "data/events",
        write_jsonl: bool | None = None,
    ):
        """
        初始化事件存储。

        Args:
            db_manager: AsyncDatabaseManager 实例
        """
        self.db = db_manager
        self.storage_dir = storage_dir
        # 确保目录存在
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)
        self._wal = _WalManager(self.storage_dir)
        if write_jsonl is None:
            write_jsonl = os.getenv("ASSISTANT_EVENTS_WRITE_JSONL", "false").lower() == "true"
        self._write_jsonl = write_jsonl
        self._db_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._db_worker_task: Optional[asyncio.Task] = None
        self._db_retry_max = int(os.getenv("ASSISTANT_DB_RETRY_MAX", "10"))
        self._db_retry_base = float(os.getenv("ASSISTANT_DB_RETRY_BASE", "0.5"))
        self._db_retry_max_delay = float(os.getenv("ASSISTANT_DB_RETRY_MAX_DELAY", "30"))
        self._db_retry_log_every = float(os.getenv("ASSISTANT_DB_RETRY_LOG_EVERY", "10"))
        self._db_last_retry_log: Dict[str, float] = {}
        self._token_buffers: Dict[str, List[Dict[str, Any]]] = {}

    def _get_file_path(self, session_id: int,run_id:str) -> str:
        return os.path.join(self.storage_dir, f"session_{session_id}_run_{run_id}.jsonl")

    def _event_to_dict(self, event: Event) -> Dict[str, Any]:
        return {
            "session_id": int(event.session_id),
            "run_id": str(event.run_id),
            "id": event.id,
            "seq_id": event.seq_id,
            "type": event.type,
            "data": event.data,
            "timestamp": event.timestamp or datetime.now().timestamp(),
            "meta": {
                "parent_run_id": event.parent_run_id,
                **event.metadata,
            },
        }

    def _dict_to_event(self, ev_data: Dict[str, Any]) -> Event:
        meta = ev_data.get("meta", {})
        return Event(
            id=ev_data.get("id", ""),
            session_id=ev_data.get("session_id", ""),
            run_id=ev_data.get("run_id", ""),
            seq_id=ev_data.get("seq_id", 0),
            type=ev_data.get("type", ""),
            data=ev_data.get("data"),
            parent_run_id=meta.get("parent_run_id"),
            timestamp=ev_data.get("timestamp", 0),
            metadata={k: v for k, v in meta.items()
                     if k not in ["parent_run_id"]},
        )

    def _buffer_key(self, session_id: int, run_id: str) -> str:
        return f"{int(session_id)}:{str(run_id)}"

    def _ensure_worker(self) -> None:
        if self._db_worker_task is not None and not self._db_worker_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._db_worker_task = loop.create_task(self._db_worker())

    async def _db_worker(self):
        while True:
            item = await self._db_queue.get()
            if item is None:
                break
            event_dict, wal_offset, retry_count = item
            try:
                if hasattr(self.db, "save_event"):
                    await self.db.save_event(int(event_dict.get("session_id")), event_dict)
                if wal_offset is not None:
                    await self._wal.checkpoint(
                        int(event_dict.get("session_id")),
                        str(event_dict.get("run_id")),
                        wal_offset,
                    )
            except Exception as e:
                retry_count += 1
                key = self._buffer_key(event_dict.get("session_id"), event_dict.get("run_id"))
                now = time.time()
                last_log = self._db_last_retry_log.get(key, 0.0)
                if now - last_log >= self._db_retry_log_every:
                    logger.warning(f"DB worker save failed, will retry: {e}")
                    self._db_last_retry_log[key] = now
                if retry_count <= self._db_retry_max:
                    delay = min(self._db_retry_base * (2 ** (retry_count - 1)), self._db_retry_max_delay)
                    await asyncio.sleep(delay)
                    await self._db_queue.put((event_dict, wal_offset, retry_count))
                else:
                    logger.error(
                        "DB worker retry exceeded, giving up: session_id=%s run_id=%s event_id=%s",
                        event_dict.get("session_id"),
                        event_dict.get("run_id"),
                        event_dict.get("id"),
                    )
            finally:
                self._db_queue.task_done()

    async def _enqueue_db_write(self, event_dict: Dict[str, Any], wal_offset: Optional[int]):
        self._ensure_worker()
        try:
            self._db_queue.put_nowait((event_dict, wal_offset, 0))
        except asyncio.QueueFull:
            logger.warning("DB queue full, skipping DB write (WAL retained)")

    def _is_token_event(self, event_type: str) -> bool:
        return event_type in {EventType.TOKEN.value, EventType.THINKING_TOKEN.value}

    def _is_token_start(self, event_type: str) -> bool:
        return event_type in {EventType.TOKEN_START.value, EventType.THINKING_START.value}

    def _should_flush_on(self, event_type: str) -> bool:
        if self._is_token_event(event_type):
            return False
        if self._is_token_start(event_type):
            return False
        return True

    async def _flush_token_buffer(self, session_id: int, run_id: str):
        key = self._buffer_key(session_id, run_id)
        buf = self._token_buffers.get(key)
        if not buf:
            return
        last_seq_id = buf[-1]["seq_id"]
        first_seq_id = buf[0]["seq_id"]
        token_count = sum(1 for t in buf if t["type"] == EventType.TOKEN.value)
        thinking_count = sum(1 for t in buf if t["type"] == EventType.THINKING_TOKEN.value)
        merged_text = "".join(t["text"] for t in buf)
        spans = []
        offset = 0
        for item in buf:
            part = item.get("text") or ""
            part_bytes = part.encode("utf-8")
            length = len(part_bytes)
            span_type = "t" if item["type"] == EventType.TOKEN.value else "k"
            spans.append([span_type, offset, length])
            offset += length

        spans_delta = []
        prev_offset = 0
        for span_type, abs_offset, length in spans:
            delta = abs_offset - prev_offset
            spans_delta.append([span_type, delta, length])
            prev_offset = abs_offset

        spans_str = "|".join(f"{t},{d},{l}" for t, d, l in spans_delta)
        agg_dict = {
            "session_id": int(session_id),
            "run_id": str(run_id),
            "id": uuid.uuid4().hex,
            "seq_id": last_seq_id,
            "type": "token_aggregate",
            "data": {
                "merged_text": merged_text,
                "spans": spans_str,
            },
            "timestamp": time.time(),
            "meta": {
                "start_seq_id": first_seq_id,
                "end_seq_id": last_seq_id,
                "token_count": token_count,
                "thinking_count": thinking_count,
                "spans_unit": "bytes",
                "spans_format": "delta_str",
            },
        }
        wal_offset = None
        try:
            wal_offset = await self._wal.append(agg_dict)
        except Exception as e:
            logger.error(f"WAL append failed for aggregate: {e}")
        if self._write_jsonl:
            await self._save_to_jsonl(session_id, run_id, agg_dict)
        await self._enqueue_db_write(agg_dict, wal_offset)
        self._token_buffers.pop(key, None)
    
    async def _load_from_jsonl(self, session_id: int, run_id: str) -> List[dict]:
        file_path = self._get_file_path(session_id, run_id)
        if not os.path.exists(file_path):
            return []
            
        try:
            def _sync_read():
                events = []
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line))
                return events
            
            return await asyncio.to_thread(_sync_read)
        except Exception as e:
            logger.error(f"Failed to read events from JSONL: {e}")
            return []
    
    async def _save_to_jsonl(self, session_id: int, run_id: str, data: dict):
        file_path = self._get_file_path(session_id, run_id)
        try:
            # 使用同步写并在线程池运行，防止阻塞
            def _sync_append():
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
            
            await asyncio.to_thread(_sync_append)
        except Exception as e:
            logger.error(f"Failed to write event to JSONL: {e}")
            
    async def save_event(self, event: Event) -> None:
        """保存事件，包含降级逻辑"""
        event_dict = self._event_to_dict(event)
        # 0. WAL append (write-ahead)
        try:
            wal_offset = await self._wal.append(event_dict)
        except Exception as e:
            logger.error(f"WAL append failed: {e}")
            wal_offset = None
        event_type = event_dict.get("type", "")
        if self._is_token_event(event_type):
            key = self._buffer_key(event.session_id, event.run_id)
            self._token_buffers.setdefault(key, []).append({
                "seq_id": event.seq_id,
                "type": event_type,
                "text": event_dict.get("data") or "",
            })
            return

        if self._should_flush_on(event_type):
            await self._flush_token_buffer(event.session_id, event.run_id)

        await self._enqueue_db_write(event_dict, wal_offset)

        if self._write_jsonl:
            await self._save_to_jsonl(event.session_id, event.run_id, event_dict)

    async def get_events(self, session_id: int, run_id: str, after_seq_id: int = -1) -> List[Event]:
        """
        从数据库获取事件。

        Args:
            run_id: 运行 ID（session_id 的字符串形式）
            after_seq_id: 只返回 seq_id > 此值的事件

        Returns:
            按 seq_id 排序的事件列表
        """
        """获取事件，包含合并/降级逻辑"""
        session_id = int(session_id)
        run_id = str(run_id)
        all_events_data = []

        # 1. 尝试从数据库加载
        try:
            if hasattr(self.db, "load_events"):
                db_events = await self.db.load_events(session_id, run_id, seq_id=after_seq_id)
                all_events_data.extend(db_events)
        except Exception as e:
            logger.debug(f"DB load_events unavailable: {e}")

        # 2. 如果数据库没数据，尝试从本地 JSONL 加载
        if not all_events_data and self._write_jsonl:
            all_events_data = await self._load_from_jsonl(session_id, run_id)

        # 3. 尝试从 WAL 读取未 flush 的事件（无论 DB/JSONL 是否命中）
        try:
            wal_events = await self._wal.read_pending(session_id, run_id)
            all_events_data.extend(wal_events)
        except Exception as e:
            logger.debug(f"WAL read pending failed: {e}")

        # 3. 转换、过滤和排序
        result = []
        seen = set()
        for ev_data in all_events_data:
            seq_id = ev_data.get("seq_id", 0)
            if seq_id <= after_seq_id:
                continue
            dedupe_key = (ev_data.get("run_id"), ev_data.get("seq_id"), ev_data.get("id"))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            # Expand aggregated token events on replay.
            if ev_data.get("type") == "token_aggregate":
                meta = ev_data.get("meta", {})
                token_count = int(meta.get("token_count", 0))
                thinking_count = int(meta.get("thinking_count", 0))
                total_count = token_count + thinking_count
                start_seq_id = int(meta.get("start_seq_id", max(1, seq_id - total_count + 1)))
                data = ev_data.get("data") or {}
                merged_text = data.get("merged_text", "")
                spans_raw = data.get("spans") or []
                text = data.get("text", "")
                thinking_text = data.get("thinking_text", "")

                spans = []
                if isinstance(spans_raw, str) and spans_raw:
                    prev_offset = 0
                    for part in spans_raw.split("|"):
                        items = part.split(",")
                        if len(items) != 3:
                            continue
                        span_type, delta_str, length_str = items
                        try:
                            delta = int(delta_str)
                            length = int(length_str)
                        except ValueError:
                            continue
                        abs_offset = prev_offset + delta
                        spans.append([span_type, abs_offset, length])
                        prev_offset = abs_offset
                elif isinstance(spans_raw, list):
                    spans = spans_raw

                if merged_text and spans:
                    merged_bytes = merged_text.encode("utf-8")
                    seq_cursor = start_seq_id
                    for span in spans:
                        if not isinstance(span, list) or len(span) != 3:
                            continue
                        span_type, offset, length = span
                        try:
                            chunk_bytes = merged_bytes[offset:offset + length]
                            chunk = chunk_bytes.decode("utf-8")
                        except Exception:
                            chunk = merged_bytes[offset:offset + length].decode("utf-8", errors="replace")

                        event_type = EventType.TOKEN.value if span_type == "t" else EventType.THINKING_TOKEN.value
                        result.append(Event(
                            id=f"{ev_data.get('id')}:{seq_cursor}",
                            session_id=ev_data.get("session_id", ""),
                            run_id=ev_data.get("run_id", ""),
                            seq_id=seq_cursor,
                            type=event_type,
                            data=chunk,
                            timestamp=ev_data.get("timestamp", 0),
                            parent_run_id=meta.get("parent_run_id"),
                            metadata={k: v for k, v in meta.items()
                                     if k not in ["parent_run_id"]},
                        ))
                        seq_cursor += 1
                    continue

                def _split_text(s: str, n: int) -> List[str]:
                    if n <= 0:
                        return []
                    if not s:
                        return [""] * n
                    # Prefer splitting on word/whitespace boundaries for smoother replay.
                    tokens = re.findall(r"\S+|\s+", s)
                    if len(tokens) < n:
                        # Fallback to character splitting if not enough tokens.
                        size, extra = divmod(len(s), n)
                        parts = []
                        idx = 0
                        for i in range(n):
                            step = size + (1 if i < extra else 0)
                            parts.append(s[idx:idx + step])
                            idx += step
                        return parts

                    # Greedy balance by target length.
                    total_len = len(s)
                    target = max(1, total_len // n)
                    parts = []
                    buf = ""
                    for tok in tokens:
                        if len(parts) < n - 1 and len(buf) + len(tok) > target and buf:
                            parts.append(buf)
                            buf = tok
                        else:
                            buf += tok
                    parts.append(buf)

                    # Normalize parts count to n.
                    if len(parts) < n:
                        parts.extend([""] * (n - len(parts)))
                    elif len(parts) > n:
                        tail = "".join(parts[n-1:])
                        parts = parts[:n-1] + [tail]
                    return parts

                token_chunks = _split_text(text, token_count)
                thinking_chunks = _split_text(thinking_text, thinking_count)

                order = meta.get("order", "")
                if not order:
                    order = ("t" * token_count) + ("k" * thinking_count)

                seq_cursor = start_seq_id
                for ch in order:
                    if ch == "t" and token_chunks:
                        chunk = token_chunks.pop(0)
                        result.append(Event(
                            id=f"{ev_data.get('id')}:{seq_cursor}",
                            session_id=ev_data.get("session_id", ""),
                            run_id=ev_data.get("run_id", ""),
                            seq_id=seq_cursor,
                            type=EventType.TOKEN.value,
                            data=chunk,
                            timestamp=ev_data.get("timestamp", 0),
                            parent_run_id=meta.get("parent_run_id"),
                            metadata={k: v for k, v in meta.items()
                                     if k not in ["parent_run_id"]},
                        ))
                    elif ch == "k" and thinking_chunks:
                        chunk = thinking_chunks.pop(0)
                        result.append(Event(
                            id=f"{ev_data.get('id')}:{seq_cursor}",
                            session_id=ev_data.get("session_id", ""),
                            run_id=ev_data.get("run_id", ""),
                            seq_id=seq_cursor,
                            type=EventType.THINKING_TOKEN.value,
                            data=chunk,
                            timestamp=ev_data.get("timestamp", 0),
                            parent_run_id=meta.get("parent_run_id"),
                            metadata={k: v for k, v in meta.items()
                                     if k not in ["parent_run_id"]},
                        ))
                    seq_cursor += 1
            else:
                result.append(self._dict_to_event(ev_data))

        result.sort(key=lambda x: x.seq_id)
        return result


class _WalManager:
    """Simple WAL + index manager."""

    def __init__(self, base_dir: str):
        self._wal_dir = os.path.join(base_dir, "wal")
        os.makedirs(self._wal_dir, exist_ok=True)
        self._locks: Dict[str, asyncio.Lock] = {}

    def _key(self, session_id: int, run_id: str) -> str:
        return f"{session_id}:{run_id}"

    def _paths(self, session_id: int, run_id: str):
        safe_run_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(run_id))
        base = f"session_{session_id}_run_{safe_run_id}"
        return (
            os.path.join(self._wal_dir, f"{base}.wal"),
            os.path.join(self._wal_dir, f"{base}.idx"),
            os.path.join(self._wal_dir, f"{base}.ckpt"),
        )

    def _get_lock(self, session_id: int, run_id: str) -> asyncio.Lock:
        key = self._key(session_id, run_id)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def append(self, event_dict: Dict[str, Any]) -> int:
        session_id = int(event_dict.get("session_id"))
        run_id = str(event_dict.get("run_id"))
        wal_path, idx_path, _ = self._paths(session_id, run_id)
        lock = self._get_lock(session_id, run_id)

        def _sync_append():
            os.makedirs(os.path.dirname(wal_path), exist_ok=True)
            line = json.dumps(event_dict, ensure_ascii=False)
            data = (line + "\n").encode("utf-8")
            with open(wal_path, "ab") as wf:
                offset = wf.tell()
                wf.write(data)
                wf.flush()
                os.fsync(wf.fileno())
            # index append
            idx_rec = {
                "seq_id": event_dict.get("seq_id"),
                "id": event_dict.get("id"),
                "offset": offset,
                "checksum": hashlib.sha256(line.encode("utf-8")).hexdigest(),
            }
            with open(idx_path, "a", encoding="utf-8") as idx:
                idx.write(json.dumps(idx_rec, ensure_ascii=False) + "\n")
                idx.flush()
                os.fsync(idx.fileno())
            return offset + len(data)

        async with lock:
            return await asyncio.to_thread(_sync_append)

    async def checkpoint(self, session_id: int, run_id: str, offset: int) -> None:
        _, _, ckpt_path = self._paths(session_id, run_id)
        lock = self._get_lock(session_id, run_id)

        def _sync_ckpt():
            with open(ckpt_path, "w", encoding="utf-8") as f:
                f.write(str(offset))
                f.flush()
                os.fsync(f.fileno())

        async with lock:
            await asyncio.to_thread(_sync_ckpt)

    async def _read_checkpoint(self, session_id: int, run_id: str) -> int:
        _, _, ckpt_path = self._paths(session_id, run_id)
        if not os.path.exists(ckpt_path):
            return 0
        def _sync_read():
            with open(ckpt_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
                return int(raw) if raw else 0
        return await asyncio.to_thread(_sync_read)

    async def read_pending(self, session_id: int, run_id: str) -> List[Dict[str, Any]]:
        wal_path, _, _ = self._paths(session_id, run_id)
        if not os.path.exists(wal_path):
            return []
        offset = await self._read_checkpoint(session_id, run_id)

        def _sync_read():
            events = []
            with open(wal_path, "rb") as f:
                f.seek(offset)
                for raw in f:
                    line = raw.decode("utf-8").strip()
                    if line:
                        events.append(json.loads(line))
            return events

        return await asyncio.to_thread(_sync_read)

    async def flush_to_db(self, db, session_id: int, run_id: str) -> None:
        pending = await self.read_pending(session_id, run_id)
        if not pending:
            return
        # best-effort flush; db layer should be idempotent
        for ev in pending:
            await db.save_event(session_id, ev)
        # advance checkpoint to end of file
        wal_path, _, _ = self._paths(session_id, run_id)
        def _sync_end_offset():
            with open(wal_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                return f.tell()
        end_offset = await asyncio.to_thread(_sync_end_offset)
        await self.checkpoint(session_id, run_id, end_offset)
