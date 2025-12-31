from abc import ABC, abstractmethod
import asyncio
from enum import Enum
from typing import Any, AsyncGenerator, Optional,Union,TypeVar
from goose.events.bus import IEventBus
from goose.events.store import IEventStore
from goose.events.types import Event
import logging
from pydantic import BaseModel
E = TypeVar("E", bound=BaseModel)

logger = logging.getLogger(__name__)

class IStreamer(ABC):
    """[业务层接口] 门面"""
    @abstractmethod
    async def emit(self, event_type: Union[str, Enum], data: Any, **kwargs) -> None:
        pass

    @abstractmethod
    async def sync_history(self) -> AsyncGenerator[E, None]:
        """拉取全量历史 (DB)"""
        pass

    @abstractmethod
    async def listen(self, after_seq_id: int = -1) -> AsyncGenerator[E, None]:
        """监听流 (Memory Bus + Backfill)"""
        pass
    
class BaseStreamer(IStreamer):
    """
    [基础层] 通用流式管理器。
    职责：
    1. 维护 seq_id。
    2. 统一 Enum -> str 转换。
    3. 协调 Bus 和 Persister。
    """
    def __init__(
        self, 
        run_id: str, 
        bus: IEventBus, 
        store: IEventStore
    ):
        self.run_id = run_id
        self.bus = bus
        self.store = store
        self._seq_counter = 0

    async def emit(self, event_type: Union[str, Enum], data: Any, producer_id: str = None, **metadata) -> None:
        self._seq_counter += 1
        
        # 统一类型转换
        type_str = event_type.value if isinstance(event_type, Enum) else str(event_type)
        
        event = Event(
            run_id=self.run_id,
            seq_id=self._seq_counter,
            type=type_str,
            data=data,
            producer_id=producer_id,
            metadata=metadata
        )

        # 1. 内存广播 (Fast path)
        await self.bus.publish(self.run_id, event)

        # 2. 异步持久化 (Slow path)
        # 策略：关键生命周期事件必须落地，高频 Token 流可以 Fire-and-forget
        is_critical = type_str.endswith("_completed") or type_str.endswith("_ended") or type_str.endswith("_failed") or type_str.endswith("_succeeded") or type_str.endswith("_started")
        
        if is_critical:
            await self._safe_save(event)
        else:
            asyncio.create_task(self._safe_save(event))

    async def listen(self, after_seq_id: int = -1) -> AsyncGenerator[Event, None]:
        """智能混合监听 (热数据 + Backfill)"""
        async for event in self.bus.subscribe(self.run_id, after_seq_id=after_seq_id):
            yield event
            
    async def sync_history(self) -> AsyncGenerator[Event, None]:
        """纯冷数据拉取"""
        events = await self.store.get_events(self.run_id)
        for evt in events:
            yield evt
    
    async def _safe_save(self, event: Event):
        try:
            await self.store.save_event(event)
        except Exception as e:
            logger.error(f"EventStore save failed: {e}")