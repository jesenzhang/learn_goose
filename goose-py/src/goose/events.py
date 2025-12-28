import asyncio
import logging
from enum import Enum
from typing import List, Dict, Any, Union, Literal, AsyncIterator, Set
from pydantic import BaseModel, Field

logger = logging.getLogger("goose.events")

# --- 事件定义 (保持之前的定义，略作增强) ---
class EventType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATE = "state"
    ERROR = "error"

class BaseEvent(BaseModel):
    timestamp: float = Field(default_factory=lambda: __import__("time").time())

class TextEvent(BaseEvent):
    type: Literal[EventType.TEXT] = EventType.TEXT
    text: str

class ToolCallEvent(BaseEvent):
    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    tool_name: str
    tool_args: Dict[str, Any]
    tool_call_id: str

class ToolResultEvent(BaseEvent):
    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT
    tool_name: str
    tool_output: str
    is_error: bool

class StateEvent(BaseEvent):
    type: Literal[EventType.STATE] = EventType.STATE
    status: str # "idle", "thinking", "tooling", "suspended"

class ErrorEvent(BaseEvent):
    type: Literal[EventType.ERROR] = EventType.ERROR
    message: str

StreamerEvent = Union[TextEvent, ToolCallEvent, ToolResultEvent, StateEvent, ErrorEvent]

# --- 核心：Broadcast Event Bus ---

class EventBus:
    """
    模拟 Rust 的 tokio::broadcast::channel
    支持多消费者订阅模式。
    """
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: StreamerEvent):
        """将事件推送到所有活跃的订阅者队列中"""
        async with self._lock:
            # 复制集合防止迭代时修改
            for q in list(self._subscribers):
                try:
                    # 使用 put_nowait 防止某个慢消费者阻塞所有人
                    # 生产级实现可能需要设置 maxsize 并丢弃旧消息
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("Subscriber queue full, dropping event")

    async def subscribe(self) -> AsyncIterator[StreamerEvent]:
        """创建一个订阅者队列并 yield"""
        q = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(q)
        
        try:
            while True:
                # 这是一个无限流，消费者通过 break 退出
                event = await q.get()
                yield event
        finally:
            # 清理订阅
            async with self._lock:
                self._subscribers.discard(q)
                logger.debug("Subscriber disconnected")