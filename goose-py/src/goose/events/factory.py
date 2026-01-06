from typing import Type, TypeVar
from .streamer import BaseStreamer
from .bus import IEventBus
from .store import IEventStore

T = TypeVar("T", bound=BaseStreamer)

class StreamerFactory:
    """
    负责生产绑定到特定 run_id 的 Streamer 实例。
    """
    def __init__(self, bus: IEventBus, store: IEventStore):
        self._bus = bus
        self._store = store

    def create(self, run_id: str, streamer_cls: Type[T] = BaseStreamer) -> T:
        return streamer_cls(
            run_id=run_id,
            bus=self._bus,
            store=self._store
        )
        