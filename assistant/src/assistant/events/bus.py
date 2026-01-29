from abc import ABC, abstractmethod
from typing import Set,Dict, TypeVar, Generic,AsyncGenerator
from pydantic import BaseModel
import asyncio
import time
import logging
from collections import defaultdict, deque
from .types import Event

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=BaseModel)

class IEventBus(ABC,Generic[E]):
    """
    [传输层接口]
    定义一个支持发布订阅、且具备一定"短时记忆"能力的事件总线。
    """
    @abstractmethod
    async def publish(self, topic: str, event: E) -> None:
        """
        发布事件到指定 Topic。
        实现应保证非阻塞 (Non-blocking)，高吞吐。
        """
        pass

    @abstractmethod
    def subscribe(self, topic: str, after_seq_id: int = -1) -> AsyncGenerator[E, None]:
        """
        订阅 Topic。
        :param after_seq_id: 
            -1 表示只订阅最新产生的实时数据 (Broadcast)。
            >=0 表示尝试从内存缓冲区中补发该序号之后的数据 (Backfill)。
        """
        pass
    
    @abstractmethod
    async def close_topic(self, topic: str) -> None:
        """关闭 Topic，断开所有连接"""
        pass

class MemoryEventBus0(IEventBus[Event]):
    """
    [企业级实现] 内存事件总线
    
    架构特点：
    1. RingBuffer: 每个 Topic 维护一个有限大小的 deque (e.g. 1000条)，作为热数据缓存。
    2. Offset Aware: 订阅时可指定 seq_id，自动从 RingBuffer 中补齐差距，实现无缝重连。
    3. Zero Blocking: 发布完全异步，消费端慢不影响生产端。
    4. Auto Expiry: 基于 TTL 自动清理闲置 Topic。
    """
    def __init__(self, buffer_size: int = 1000, ttl: int = 3600):
        # topic -> Set[Queue]
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        # topic -> deque[Event] (RingBuffer)
        self._buffers: Dict[str, deque[Event]] = defaultdict(lambda: deque(maxlen=buffer_size))
        # topic -> last_active_time
        self._access_log: Dict[str, float] = {}
        
        self._ttl = ttl
        self._bg_task = asyncio.create_task(self._gc_loop())

    async def publish(self, topic: str, event: Event) -> None:
        self._access_log[topic] = time.time()
        
        # 1. 写入 RingBuffer (热数据缓存)
        self._buffers[topic].append(event)
        
        # 2. 广播给实时订阅者
        if topic in self._subscribers:
            # Snapshot set to avoid runtime modification errors
            for q in list(self._subscribers[topic]):
                try:
                    # Non-blocking put. If consumer is dead/slow, drop frame to protect producer.
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # 生产环境建议增加监控指标
                    logger.warning(f"Drop event {event.seq_id} for topic {topic} (Consumer slow)")
                except Exception:
                    pass # Closed queue

    def subscribe(self, topic: str, after_seq_id: int = -1) -> AsyncGenerator[Event, None]:
        self._access_log[topic] = time.time()
        
        # 申请一个带背压保护的队列
        q = asyncio.Queue(maxsize=1000)
        
        # --- 阶段 1: 内存回填 (Backfill) ---
        # 如果客户端请求补发，且缓存里有，先塞进队列
        if topic in self._buffers and after_seq_id >= 0:
            for event in self._buffers[topic]:
                if event.seq_id > after_seq_id:
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.warning(f"Backfill buffer full for {topic}")
                        break
        
        # --- 阶段 2: 注册实时监听 ---
        if topic not in self._subscribers:
            self._subscribers[topic] = set()
        self._subscribers[topic].add(q)
        
        # --- 阶段 3: 生成器逻辑 ---
        async def _generator():
            try:
                while True:
                    event = await q.get()
                    if event is None: # Sentinel
                        break
                    yield event
            finally:
                # Cleanup
                if topic in self._subscribers:
                    self._subscribers[topic].discard(q)
                    if not self._subscribers[topic]:
                        # Remove key from subscribers map, but keep buffer/history for TTL
                        del self._subscribers[topic]
        
        return _generator()

    async def close_topic(self, topic: str) -> None:
        if topic in self._subscribers:
            for q in list(self._subscribers[topic]):
                await q.put(None)
    
    async def _gc_loop(self):
        """垃圾回收：清理长时间不活动的 Topic 缓存"""
        while True:
            await asyncio.sleep(600)
            now = time.time()
            dead_topics = [t for t, last in self._access_log.items() if now - last > self._ttl]
            for t in dead_topics:
                # 只有在没有活跃订阅者时才清理缓存
                if t not in self._subscribers:
                    self._buffers.pop(t, None)
                    self._access_log.pop(t, None)
                    logger.debug(f"GC: Cleaned up topic {t}")
                    


class MemoryEventBus(IEventBus[Event]):
    def __init__(self, buffer_size: int = 1000, ttl: int = 3600):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._buffers: Dict[str, deque[Event]] = defaultdict(lambda: deque(maxlen=buffer_size))
        self._access_log: Dict[str, float] = {}
        self._ttl = ttl
        self._gc_task = asyncio.create_task(self._gc_loop())
        

    async def publish(self, topic: str, event: Event) -> None:
        self._access_log[topic] = time.time()

        # 写 ring buffer
        self._buffers[topic].append(event)

        # 广播
        for q in list(self._subscribers.get(topic, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Drop event {event.seq_id} for topic {topic}")
            except Exception:
                pass

    def subscribe(self, topic: str, after_seq_id: int = -1) -> AsyncGenerator[Event, None]:
        self._access_log[topic] = time.time()
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)

        # ---------- Phase 0: RingBuffer 回填 ----------
        if after_seq_id >= 0:
            for event in self._buffers.get(topic, []):
                if event.seq_id > after_seq_id:
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        break

        # ---------- Phase 1: 同步注册 subscriber（关键） ----------
        self._subscribers[topic].add(q)

        # ---------- Phase 2: Generator ----------
        async def _gen():
            try:
                while True:
                    evt = await q.get()
                    if evt is None:
                        break
                    yield evt
            finally:
                self._subscribers[topic].discard(q)
                if not self._subscribers[topic]:
                    self._subscribers.pop(topic, None)

        return _gen()

    async def close_topic(self, topic: str) -> None:
        for q in list(self._subscribers.get(topic, [])):
            await q.put(None)

    async def _gc_loop(self):
        while True:
            await asyncio.sleep(600)
            now = time.time()
            for topic, last in list(self._access_log.items()):
                if now - last > self._ttl and topic not in self._subscribers:
                    self._buffers.pop(topic, None)
                    self._access_log.pop(topic, None)
