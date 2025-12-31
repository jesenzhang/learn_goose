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


class SQLEventStore(IEventStore):
    def __init__(self,pm:PersistenceManager):
        self.pm = pm
        # 注册表结构
        self.pm.register_schema("""
        CREATE TABLE IF NOT EXISTS workflow_events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            seq_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            timestamp REAL,
            event_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_run_id ON workflow_events(run_id);
        """)

    async def save_event(self, event: Event) -> None:
        # 实际生产中建议批量插入优化性能，这里演示单条插入
        await self.pm.execute(
            "INSERT INTO workflow_events (id, run_id, seq_id, type, timestamp, event_json) VALUES (?, ?, ?, ?, ?, ?)",
            (event.id, event.run_id, event.seq_id, event.type.value, event.timestamp, event.model_dump_json())
        )

    async def get_events(self, run_id: str, start_seq_id: int = 0) -> List[Event]:
        rows = await self.pm.fetch_all(
            "SELECT event_json FROM workflow_events WHERE run_id = ? AND seq_id > ? ORDER BY seq_id ASC",
            (run_id, start_seq_id)
        )
        return [Event.model_validate_json(row["event_json"]) for row in rows]