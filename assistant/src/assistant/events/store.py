"""
Event Store - 适配 AsyncDatabaseManager 到 IEventStore 接口。
"""
import logging
from typing import List, TypeVar,Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel
import os
import json
import asyncio
from datetime import datetime
from .types import Event

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

    def __init__(self, db_manager,storage_dir: str = "data/events"):
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

    def _get_file_path(self, session_id: int,run_id:str) -> str:
        return os.path.join(self.storage_dir, f"session_{session_id}_run_{run_id}.jsonl")
    
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
        # 构建统一的字典格式
        event_dict = {
            "session_id": int(event.session_id),
            "run_id": str(event.run_id),
            "id": event.id,
            "seq_id": event.seq_id,
            "type": event.type,
            "data": event.data,
            "timestamp": event.timestamp or datetime.now().timestamp(),
            "meta": {
                "producer_id": event.producer_id,
                "parent_run_id": event.parent_run_id,
                **event.metadata
            }
        }
        # 1. 尝试保存到数据库 (如果 db 实现支持 save_event)
        try:
            if hasattr(self.db, "save_event"):
                await self.db.save_event(event.session_id, event_dict)
                await self._save_to_jsonl(event.session_id, event.run_id, event_dict)
                return # 成功则返回
        except Exception as e:
            logger.warning(f"DB save_event failed, falling back to JSONL: {e}")

        # 2. 降级：保存到本地 JSONL
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
                db_events = await self.db.load_events(session_id,run_id)
                all_events_data.extend(db_events)
        except Exception as e:
            logger.debug(f"DB load_events unavailable: {e}")

        # 2. 如果数据库没数据，尝试从本地 JSONL 加载
        if not all_events_data:
            all_events_data = await self._load_from_jsonl(session_id, run_id)

        # 3. 转换、过滤和排序
        result = []
        for ev_data in all_events_data:
            seq_id = ev_data.get("seq_id", 0)
            if seq_id <= after_seq_id:
                continue

            meta = ev_data.get("meta", {})
            result.append(Event(
                id=ev_data.get("id", ""),
                session_id=ev_data.get("session_id", ""),
                run_id=ev_data.get("run_id", ""),
                seq_id=ev_data.get("seq_id", 0),
                type=ev_data.get("type", ""),
                data=ev_data.get("data"),
                producer_id=meta.get("producer_id"),
                parent_run_id=meta.get("parent_run_id"),
                timestamp=ev_data.get("timestamp", 0),
                metadata={k: v for k, v in meta.items() 
                         if k not in ["producer_id", "parent_run_id"]}
            ))
        
        result.sort(key=lambda x: x.seq_id)
        return result
