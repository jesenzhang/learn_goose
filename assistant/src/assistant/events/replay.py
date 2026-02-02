"""
事件回放管理器 - 支持历史事件回放和事件流管理
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ReplayMode(Enum):
    """回放模式"""
    LIVE = "live"  # 实时推送事件
    REPLAY = "replay"  # 历史回放
    SYNC = "sync"  # 同步模式（阻塞直到事件结束）


class EventReplayManager:
    """事件回放管理器"""

    def __init__(self, store, cache_size: int | None = None, batch_size: int | None = None):
        """
        初始化事件回放管理器

        Args:
            db: 数据库管理器实例
        """
        self.store = store
        self.active_replays: Dict[str, asyncio.Queue] = {}
        self.event_listeners: Dict[str, List[Callable]] = {}
        self._cache: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        if cache_size is None:
            cache_size = int(os.getenv("ASSISTANT_REPLAY_CACHE_SIZE", "64"))
        self._cache_size = cache_size
        if batch_size is None:
            batch_size = int(os.getenv("ASSISTANT_REPLAY_BATCH_SIZE", "200"))
        self._batch_size = batch_size

    async def start_replay(
        self,
        session_id: str,
        mode: ReplayMode = ReplayMode.LIVE,
        since: Optional[str] = None,
        run_id: str = "",
        after_seq_id: int = -1,
    ) -> asyncio.Queue:
        """
        开始事件回放

        Args:
            session_id: 会话 ID
            mode: 回放模式
            since: 起始时间（ISO 格式），用于历史回放

        Returns:
            事件队列，用于接收事件
        """
        if session_id in self.active_replays:
            logger.warning(f"Replay already exists for session {session_id}")
            return self.active_replays[session_id]

        queue = asyncio.Queue(maxsize=1000)
        self.active_replays[session_id] = queue

        if mode == ReplayMode.REPLAY:
            await self._load_historical_events(
                session_id,
                run_id,
                since,
                after_seq_id,
                queue,
            )
        elif mode == ReplayMode.LIVE:
            await self._emit_live_event(
                session_id,
                {"type": "replay_started", "mode": mode.value},
                queue
            )

        logger.info(f"Started {mode.value} replay for session {session_id}")
        return queue

    async def _load_historical_events(
        self,
        session_id: str,
        run_id: str,
        since: Optional[str],
        after_seq_id: int,
        queue: asyncio.Queue
    ):
        """加载历史事件"""
        try:
            t0 = time.monotonic()
            cache_key = f"{session_id}:{run_id}:{after_seq_id}:{since or ''}"
            events = self._cache_get(cache_key)
            cache_hit = events is not None
            t_cache = time.monotonic()
            if events is None:
                raw = await self.store.get_events(int(session_id), run_id, after_seq_id=after_seq_id)
                t_fetch = time.monotonic()
                events = [e if isinstance(e, dict) else e.model_dump() for e in raw]
                t_convert = time.monotonic()
                if since:
                    try:
                        since_dt = datetime.fromisoformat(since)
                        events = [
                            e for e in events
                            if e.get("timestamp") and datetime.fromisoformat(str(e.get("timestamp"))) >= since_dt
                        ]
                        t_filter = time.monotonic()
                    except Exception:
                        t_filter = time.monotonic()
                        pass
                self._cache_put(cache_key, events)
                t_cache_put = time.monotonic()
            else:
                t_fetch = t_convert = t_filter = t_cache_put = t_cache
            logger.info(f"Loaded {len(events)} historical events for session {session_id}")
            logger.debug(
                "replay load timing: session_id=%s run_id=%s after_seq_id=%s since=%s cache_hit=%s "
                "t_cache=%.2fms t_fetch=%.2fms t_convert=%.2fms t_filter=%.2fms t_cache_put=%.2fms total=%.2fms",
                session_id,
                run_id,
                after_seq_id,
                since,
                cache_hit,
                (t_cache - t0) * 1000,
                (t_fetch - t_cache) * 1000,
                (t_convert - t_fetch) * 1000,
                (t_filter - t_convert) * 1000,
                (t_cache_put - t_filter) * 1000,
                (t_cache_put - t0) * 1000,
            )

            if self._batch_size <= 0:
                self._batch_size = 200
            count = 0
            t_emit = time.monotonic()
            for event in events:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    await queue.put(event)
                count += 1
                if count % self._batch_size == 0:
                    await asyncio.sleep(0)
            logger.debug(
                "replay emit timing: session_id=%s run_id=%s count=%s batch_size=%s emit_ms=%.2f",
                session_id,
                run_id,
                count,
                self._batch_size,
                (time.monotonic() - t_emit) * 1000,
            )

            await queue.put({
                "type": "replay_complete",
                "count": len(events),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to load historical events: {e}")
            await queue.put({
                "type": "replay_error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })

    def _cache_get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        events = self._cache.get(key)
        if events is None:
            return None
        self._cache.move_to_end(key)
        return events

    def _cache_put(self, key: str, events: List[Dict[str, Any]]) -> None:
        self._cache[key] = events
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    async def _emit_live_event(
        self,
        session_id: str,
        event: Dict[str, Any],
        queue: Optional[asyncio.Queue] = None
    ):
        """发送实时事件"""
        if session_id in self.active_replays:
            target_queue = self.active_replays[session_id]
            try:
                if not target_queue.full():
                    await target_queue.put(event)
                else:
                    logger.warning(f"Event queue full for session {session_id}")
            except asyncio.QueueFull:
                logger.warning(f"Failed to emit event, queue full: {session_id}")

        if queue:
            try:
                await queue.put(event)
            except asyncio.QueueFull:
                pass

    async def stop_replay(self, session_id: str):
        """停止事件回放"""
        if session_id in self.active_replays:
            queue = self.active_replays[session_id]
            await queue.put({
                "type": "replay_stopped",
                "timestamp": datetime.now().isoformat()
            })
            del self.active_replays[session_id]
            logger.info(f"Stopped replay for session {session_id}")

    def add_listener(self, event_type: str, callback: Callable):
        """添加事件监听器"""
        if event_type not in self.event_listeners:
            self.event_listeners[event_type] = []
        self.event_listeners[event_type].append(callback)
        logger.debug(f"Added listener for event type: {event_type}")

    def remove_listener(self, event_type: str, callback: Callable):
        """移除事件监听器"""
        if event_type in self.event_listeners:
            try:
                self.event_listeners[event_type].remove(callback)
            except ValueError:
                pass

    async def notify_listeners(self, event: Dict[str, Any]):
        """通知事件监听器"""
        event_type = event.get("type")
        if event_type in self.event_listeners:
            for callback in self.event_listeners[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Listener callback error: {e}")

    async def export_events(
        self,
        session_id: str,
        output_file: str,
        since: Optional[str] = None,
        until: Optional[str] = None
    ) -> int:
        """
        导出事件到文件

        Args:
            session_id: 会话 ID
            output_file: 输出文件路径
            since: 起始时间
            until: 结束时间

        Returns:
            导出的事件数量
        """
        try:
            events = await self.store.get_events(int(session_id), run_id="", after_seq_id=-1)

            if until:
                until_dt = datetime.fromisoformat(until)
                events = [
                    e for e in events
                    if datetime.fromisoformat(e.get("timestamp", "")) <= until_dt
                ]

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)

            logger.info(f"Exported {len(events)} events to {output_file}")
            return len(events)
        except Exception as e:
            logger.error(f"Failed to export events: {e}")
            raise

    async def import_events(
        self,
        session_id: str,
        input_file: str
    ) -> int:
        """
        从文件导入事件

        Args:
            session_id: 会话 ID
            input_file: 输入文件路径

        Returns:
            导入的事件数量
        """
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                events = json.load(f)

            count = 0
            for event in events:
                if await self.store.save_event(event):
                    count += 1

            logger.info(f"Imported {count} events from {input_file}")
            return count
        except Exception as e:
            logger.error(f"Failed to import events: {e}")
            raise

    async def get_event_stats(self, session_id: str) -> Dict[str, Any]:
        """获取事件统计信息"""
        try:
            events = await self.store.get_events(int(session_id), run_id="", after_seq_id=-1)

            stats = {
                "total_events": len(events),
                "event_types": {},
                "time_range": {
                    "start": None,
                    "end": None
                }
            }

            if events:
                timestamps = [
                    datetime.fromisoformat(e.get("timestamp", ""))
                    for e in events
                    if e.get("timestamp")
                ]
                if timestamps:
                    stats["time_range"]["start"] = min(timestamps).isoformat()
                    stats["time_range"]["end"] = max(timestamps).isoformat()

                for event in events:
                    event_type = event.get("type", "unknown")
                    stats["event_types"][event_type] = \
                        stats["event_types"].get(event_type, 0) + 1

            return stats
        except Exception as e:
            logger.error(f"Failed to get event stats: {e}")
            return {}
