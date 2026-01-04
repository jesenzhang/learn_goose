from abc import ABC, abstractmethod
from typing import List,Dict, TypeVar, Generic,AsyncGenerator
from goose.events.types import Event
from goose.persistence.manager import PersistenceManager
from pydantic import BaseModel

E = TypeVar("E", bound=BaseModel)

# --- Trait ---

class IEventStore(ABC):
    """[存储层接口]"""
    @abstractmethod
    async def save_event(self, event: E) -> None:
        pass

    @abstractmethod
    async def get_events(self, run_id: str, after_seq_id: int = -1) -> List[E]:
        """获取历史事件，支持分页或增量拉取"""
        pass

# --- Implementation ---

WORKFLOW_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    seq_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    timestamp REAL,
    event_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

WORKFLOW_EVENTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_events_lookup ON workflow_events(run_id, seq_id);
"""

def register_event_store_schema():
    from goose.persistence.manager import persistence_manager
    persistence_manager.register_schema(WORKFLOW_EVENTS_TABLE_SQL)
    persistence_manager.register_schema(WORKFLOW_EVENTS_INDEX_SQL)

class SQLEventStore(IEventStore):
    def __init__(self, pm: PersistenceManager):
        self.pm = pm
        # 注册表结构
        self.pm.register_schema(WORKFLOW_EVENTS_TABLE_SQL)
        self.pm.register_schema(WORKFLOW_EVENTS_INDEX_SQL)

    async def save_event(self, event: Event) -> None:
        # 统一类型转换逻辑
        event_type = event.type
        # 兼容 Enum 和 Str
        type_str = getattr(event_type, "value", str(event_type))

        await self.pm.execute(
            """
            INSERT INTO workflow_events 
            (id, run_id, seq_id, type, timestamp, event_json) 
            VALUES (:id, :run_id, :seq_id, :type, :timestamp, :event_json)
            """,
            {
                "id": event.id,
                "run_id": event.run_id,
                "seq_id": event.seq_id,
                "type": type_str,
                "timestamp": event.timestamp,
                "event_json": event.model_dump_json()
            }
        )

    async def get_events(self, run_id: str, after_seq_id: int = -1) -> List[Event]:
        # [关键] 确保按 seq_id 正序排列，否则前端打印会乱序
        rows = await self.pm.fetch_all(
            """
            SELECT event_json FROM workflow_events 
            WHERE run_id = :run_id AND seq_id > :after_seq_id 
            ORDER BY seq_id ASC
            """,
            {
                "run_id": run_id, 
                "after_seq_id": after_seq_id
            }
        )
        # 反序列化
        return [Event.model_validate_json(row["event_json"]) for row in rows]