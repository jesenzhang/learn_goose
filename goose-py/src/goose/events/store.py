from abc import ABC, abstractmethod
from typing import List,Dict, TypeVar, Generic,AsyncGenerator
from .types import Event
import logging
from pydantic import BaseModel

from goose.persistence import BaseRepository,TableSpec,with_table

logger = logging.getLogger(__name__)

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
    data TEXT,
    parent_run_id TEXT,
    producer_id TEXT,
    timestamp REAL,
    metadata TEXT
);

"""
WORKFLOW_EVENTS_INDEX_SQL = """
-- [关键] 添加联合索引
-- 用于快速执行: SELECT * FROM events WHERE run_id = ? ORDER BY seq_id ASC
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON workflow_events(run_id, seq_id);
"""


@with_table(name='workflow_events',model=Event,sql=[WORKFLOW_EVENTS_TABLE_SQL,WORKFLOW_EVENTS_INDEX_SQL],pk='id',priority=0,attr_name='event_spec')
class SQLEventStore(BaseRepository,IEventStore):
    async def save_event(self, event: Event) -> None:
        try:
            await self._insert(Event,event)
        except Exception as e:
            logger.error(e)


    async def get_events(self, run_id: str, after_seq_id: int = -1) -> List[Event]:
        # [关键] 确保按 seq_id 正序排列，否则前端打印会乱序
        try:
            events = await self._find(Event,
                filters={
                    "run_id": run_id,
                    "seq_id":{'$gt': after_seq_id}
                }, 
                limit=10000
            )
            events.sort(key=lambda x: x.seq_id)
            return events
        except Exception as e:
            logger.error(e)
            return []
