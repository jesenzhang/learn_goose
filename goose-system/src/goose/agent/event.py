"""
Agent Event System

事件定义和事件流处理。
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
import uuid


class AgentEventType(Enum):
    """Agent 事件类型"""
    MESSAGE = auto()
    MCP_NOTIFICATION = auto()
    MODEL_CHANGE = auto()
    HISTORY_REPLACED = auto()
    TOOL_START = auto()
    TOOL_END = auto()
    TOOL_ERROR = auto()
    APPROVAL_REQUIRED = auto()
    APPROVAL_RECEIVED = auto()
    COMPACTION_STARTED = auto()
    COMPACTION_COMPLETED = auto()
    ERROR = auto()
    DONE = auto()


@dataclass
class AgentEvent:
    """Agent 事件"""
    type: AgentEventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    @classmethod
    def message(cls, content: str, role: str = "assistant") -> "AgentEvent":
        """创建消息事件"""
        return cls(
            type=AgentEventType.MESSAGE,
            data={"content": content, "role": role}
        )
    
    @classmethod
    def tool_start(cls, tool_name: str, arguments: Dict[str, Any]) -> "AgentEvent":
        """创建工具开始事件"""
        return cls(
            type=AgentEventType.TOOL_START,
            data={"tool_name": tool_name, "arguments": arguments}
        )
    
    @classmethod
    def tool_end(cls, tool_name: str, result: Any) -> "AgentEvent":
        """创建工具结束事件"""
        return cls(
            type=AgentEventType.TOOL_END,
            data={"tool_name": tool_name, "result": result}
        )
    
    @classmethod
    def tool_error(cls, tool_name: str, error: str) -> "AgentEvent":
        """创建工具错误事件"""
        return cls(
            type=AgentEventType.TOOL_ERROR,
            data={"tool_name": tool_name, "error": error}
        )
    
    @classmethod
    def approval_required(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: str
    ) -> "AgentEvent":
        """创建需要批准事件"""
        return cls(
            type=AgentEventType.APPROVAL_REQUIRED,
            data={
                "tool_name": tool_name,
                "arguments": arguments,
                "reason": reason
            }
        )
    
    @classmethod
    def model_change(cls, model: str, mode: str) -> "AgentEvent":
        """创建模型变更事件"""
        return cls(
            type=AgentEventType.MODEL_CHANGE,
            data={"model": model, "mode": mode}
        )
    
    @classmethod
    def history_replaced(cls, message_count: int) -> "AgentEvent":
        """创建历史替换事件"""
        return cls(
            type=AgentEventType.HISTORY_REPLACED,
            data={"message_count": message_count}
        )
    
    @classmethod
    def error(cls, message: str, exception: Optional[Exception] = None) -> "AgentEvent":
        """创建错误事件"""
        return cls(
            type=AgentEventType.ERROR,
            data={"message": message, "exception": str(exception) if exception else None}
        )


class EventEmitter:
    """事件发射器"""
    
    def __init__(self):
        self._handlers: Dict[AgentEventType, List[callable]] = {}
    
    def on(self, event_type: AgentEventType, handler: callable) -> None:
        """注册事件处理器"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def off(self, event_type: AgentEventType, handler: callable) -> None:
        """移除事件处理器"""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
    
    async def emit(self, event: AgentEvent) -> None:
        """发射事件"""
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")
    
    def emit_sync(self, event: AgentEvent) -> None:
        """同步发射事件"""
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")


class EventStream:
    """事件流管理器"""
    
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._emitter = EventEmitter()
        self._closed = False
    
    def __aiter__(self):
        return self
    
    async def __anext__(self) -> AgentEvent:
        """异步迭代事件流"""
        if self._closed:
            raise StopAsyncIteration
        try:
            event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            return event
        except asyncio.TimeoutError:
            if self._closed:
                raise StopAsyncIteration
            raise
    
    async def push(self, event: AgentEvent) -> None:
        """推送事件"""
        if not self._closed:
            await self._queue.put(event)
    
    def close(self) -> None:
        """关闭事件流"""
        self._closed = True
    
    @property
    def emitter(self) -> EventEmitter:
        """获取事件发射器"""
        return self._emitter


import asyncio
