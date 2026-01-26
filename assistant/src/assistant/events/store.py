"""
Event Store - 适配 AsyncDatabaseManager 到 IEventStore 接口。
"""
import logging
from typing import List, TypeVar
from abc import ABC, abstractmethod
from pydantic import BaseModel

from .types import Event

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=BaseModel)


class IEventStore(ABC):
    """[存储层接口]"""
    @abstractmethod
    async def save_event(self, event: E) -> None:
        pass

    @abstractmethod
    async def get_events(self, run_id: str, after_seq_id: int = -1) -> List[E]:
        pass


class AsyncEventStore(IEventStore):
    """
    使用 AsyncDatabaseManager 的事件存储实现。

    将 pho 的 Event 模型适配到现有的数据库结构。
    """

    def __init__(self, db_manager):
        """
        初始化事件存储。

        Args:
            db_manager: AsyncDatabaseManager 实例
        """
        self.db = db_manager

    async def save_event(self, event: Event) -> None:
        """
        保存事件到数据库。

        使用 seq_id 列（迁移后）或 metadata 存储序列信息。
        """
        try:
            import json

            # 构建事件数据
            event_data = {
                "id": event.id,
                "type": event.type,
                "data": event.data,
                "timestamp": event.timestamp,
                "seq_id": event.seq_id,
                "meta": {
                    "producer_id": event.producer_id,
                    "parent_run_id": event.parent_run_id,
                    **event.metadata
                }
            }

            # 解析 run_id 为 session_id
            session_id = int(event.run_id)

            await self.db.save_event(session_id, event_data)

        except Exception as e:
            logger.error(f"Failed to save event: {e}", exc_info=e)

    async def get_events(self, run_id: str, after_seq_id: int = -1) -> List[Event]:
        """
        从数据库获取事件。

        Args:
            run_id: 运行 ID（session_id 的字符串形式）
            after_seq_id: 只返回 seq_id > 此值的事件

        Returns:
            按 seq_id 排序的事件列表
        """
        try:
            import json

            session_id = int(run_id)

            # 从数据库加载事件
            events = await self.db.load_events(session_id)

            # 转换为 StreamerEvent 格式
            streamer_events = []
            for ev_data in events:
                # 直接从 ev_data 获取 seq_id（迁移后存在顶层）
                seq_id = ev_data.get("seq_id", 0)

                # 跳过不符合条件的
                if seq_id <= after_seq_id:
                    continue

                meta = ev_data.get("meta", {})

                streamer_event = Event(
                    id=ev_data.get("id", ""),
                    run_id=str(session_id),
                    seq_id=seq_id,
                    type=ev_data.get("type", ""),
                    data=ev_data.get("data"),
                    producer_id=meta.get("producer_id"),
                    parent_run_id=meta.get("parent_run_id"),
                    timestamp=ev_data.get("timestamp", 0),
                    metadata={k: v for k, v in meta.items()
                             if k not in ["producer_id", "parent_run_id"]}
                )
                streamer_events.append(streamer_event)

            # 按 seq_id 排序
            streamer_events.sort(key=lambda x: x.seq_id)

            return streamer_events

        except Exception as e:
            logger.error(f"Failed to get events: {e}", exc_info=e)
            return []
