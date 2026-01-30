"""
事件回放管理器 - 支持历史事件回放和事件流管理
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum
import json

from ..db import get_db

logger = logging.getLogger(__name__)


class ReplayMode(Enum):
    """回放模式"""
    LIVE = "live"  # 实时推送事件
    REPLAY = "replay"  # 历史回放
    SYNC = "sync"  # 同步模式（阻塞直到事件结束）


class EventReplayManager:
    """事件回放管理器"""

    def __init__(self, db):
        """
        初始化事件回放管理器

        Args:
            db: 数据库管理器实例
        """
        self.db = db
        self.active_replays: Dict[str, asyncio.Queue] = {}
        self.event_listeners: Dict[str, List[Callable]] = {}

    async def start_replay(
        self,
        session_id: str,
        mode: ReplayMode = ReplayMode.LIVE,
        since: Optional[str] = None
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

        if mode == ReplayMode.REPLAY and since:
            await self._load_historical_events(session_id, since, queue)
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
        since: str,
        queue: asyncio.Queue
    ):
        """加载历史事件"""
        try:
            events = await self.db.load_events(session_id, run_id="", since=since)
            logger.info(f"Loaded {len(events)} historical events for session {session_id}")

            for event in events:
                await queue.put(event)
                await asyncio.sleep(0.01)  # 模拟流式推送

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
            events = await self.db.load_events(session_id, run_id="", since=since)

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
                if await self.db.save_event(session_id, event):
                    count += 1

            logger.info(f"Imported {count} events from {input_file}")
            return count
        except Exception as e:
            logger.error(f"Failed to import events: {e}")
            raise

    async def get_event_stats(self, session_id: str) -> Dict[str, Any]:
        """获取事件统计信息"""
        try:
            events = await self.db.load_events(session_id, run_id="")

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
