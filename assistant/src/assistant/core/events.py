"""
Event Bus Module - Event-driven core for agent system.

This module provides an event-driven architecture that decouples "what happens"
from "how it's transmitted", enabling real-time streaming responses.
"""

import logging
from enum import Enum
import uuid
from typing import Any, Callable, Awaitable, List, Optional,Dict
from datetime import datetime,timezone
import time
from pydantic import BaseModel, Field
import asyncio
import weakref

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Event types for agent lifecycle and tool execution."""
    
    # === 1. 任务生命周期 (Lifecycle) ===
    RUN_START = "run_start"         # [新增] 整个任务开始（前端用于重置 UI、显示 Loading）
    DONE = "done"                   # 任务完全结束（流结束信号）
    ERROR = "error"                 # 全局致命错误

    # === 2. LLM 内容生成 (Content Generation) ===
    TOKEN_START = "token_start"     # LLM 开始生成（首字延迟统计）
    TOKEN = "token"                 # 标准文本 Token
    TOKEN_END = "token_end"         # LLM 生成结束
    
    # [新增] 深度思考/推理 Token (适配 DeepSeek-R1, o1 等模型)
    # 允许前端将“思考过程”折叠显示，与最终答案区分开
    THINKING_START = "thinking_start"
    THINKING_TOKEN = "thinking_token" 
    THINKING_END = "thinking_end"

    # === 3. 工具与执行 (Tools & Actions) ===
    STATE_CHANGE = "state_change"   # 状态变更 (Intent 确认 / Plan 更新 / 步骤切换)
    TOOL_START = "tool_start"       # 工具开始调用 (包含 input 参数)
    TOOL_END = "tool_end"           # 工具调用结束 (包含 output 结果，meta 中包含 artifacts)

    # === 4. 人机交互与控制 (Interaction) ===
    APPROVAL_REQ = "approval_req"   # 需要人工审批
    
    # [新增] 协议保活 (Keep-Alive)
    # NDJSON 模式下，如果 Agent 长时间思考不输出，需要发 Ping 包防止连接断开
    PING = "ping"

class Event(BaseModel):
    """Immutable event representation."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: EventType = None  # Event type
    data: Any = None  # Event payload
    timestamp: float = Field(default_factory=time.time)
    meta: Optional[Dict[str, Any]] = None


class EventManager:
    """
    Asynchronous event manager with listener support.

    Features:
    - Subscription-based event publishing
    - Weak reference support to prevent memory leaks
    - Async listener execution
    """

    def __init__(self):
        self._listeners: List[Callable[[Event], Awaitable[None]]] = []
        self._weak_listeners: List[weakref.ref] = []

    def subscribe(self, listener: Callable[[Event], Awaitable[None]], weak: bool = False) -> Callable[[], None]:
        """
        Subscribe to events.

        Args:
            listener: Async callback that receives Event objects
            weak: If True, use weak reference to allow garbage collection

        Returns:
            Unsubscribe callback
        """
        if weak:
            weak_ref = weakref.ref(listener, self._on_listener_gc)
            self._weak_listeners.append(weak_ref)
            return lambda: self._weak_listeners.remove(weak_ref)
        else:
            self._listeners.append(listener)
            return lambda: self._listeners.remove(listener)

    def _on_listener_gc(self, weak_ref):
        """Callback when weakly-referenced listener is garbage collected."""
        if weak_ref in self._weak_listeners:
            self._weak_listeners.remove(weak_ref)

    async def emit(self, event_type: EventType, data: Any, meta: Optional[Dict[str, Any]] = None):
        """
        Publish an event to all listeners.

        Args:
            event_type: Type of event to emit
            data: Event payload
        """
        event = Event(type=event_type, data=data, meta=meta)

        # Collect all active listeners
        active_listeners = list(self._listeners)
        for weak_ref in self._weak_listeners:
            listener = weak_ref()
            if listener is not None:
                active_listeners.append(listener)

        # Execute all listeners concurrently
        if active_listeners:
            tasks = [listener(event) for listener in active_listeners]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log listener errors without crashing
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Event listener error: {result}", exc_info=result)

    def clear(self):
        """Remove all listeners. Useful for testing or cleanup."""
        self._listeners.clear()
        self._weak_listeners.clear()
