# import asyncio
# from typing import AsyncGenerator, Set, Dict,Any

# class EventBus:
#     """
#     轻量级异步事件总线。
#     支持多播（一个事件发送给多个订阅者）。
#     """
#     def __init__(self):
#         # topic -> set of queues
#         # 这里用 run_id 作为 topic
#         self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

#     async def publish(self, topic: str, event: Any):
#         """向指定 topic 发布事件"""
#         if topic in self._subscribers:
#             # 广播给所有监听该 topic 的队列
#             # 使用 list() 复制集合防止迭代时修改
#             for q in list(self._subscribers[topic]):
#                 await q.put(event)

#     def subscribe(self, topic: str) -> AsyncGenerator[Any, None]:
#         """
#         订阅指定 topic，返回异步生成器。
#         """
#         queue = asyncio.Queue()
        
#         if topic not in self._subscribers:
#             self._subscribers[topic] = set()
#         self._subscribers[topic].add(queue)

#         async def _generator():
#             try:
#                 while True:
#                     event = await queue.get()
#                     if event is None: # 结束信号
#                         break
#                     yield event
#             finally:
#                 # 清理逻辑：生成器停止时移除订阅
#                 if topic in self._subscribers:
#                     self._subscribers[topic].discard(queue)
#                     if not self._subscribers[topic]:
#                         del self._subscribers[topic]
        
#         return _generator()

#     async def close_topic(self, topic: str):
#         """关闭某个 Topic，通知所有订阅者结束"""
#         if topic in self._subscribers:
#             for q in list(self._subscribers[topic]):
#                 await q.put(None)
    
# import asyncio
# import time
# import logging
# from collections import defaultdict, deque
# from typing import List, Callable, Dict, Any, TypeVar, Generic, Awaitable

# logger = logging.getLogger(__name__)

# # 定义泛型事件类型，解耦具体业务实体
# E = TypeVar("E")

# class MemoryEventBus(Generic[E]):
#     """
#     生产级内存事件总线。
#     特性：
#     1. 支持历史回溯 (Backfill)。
#     2. 自动内存管理 (History Limit & TTL)。
#     3. 异常隔离 (Handler 报错不影响广播)。
#     """
#     def __init__(
#         self, 
#         history_limit: int = 1000,   # 每个 Session 保留的最大事件数
#         session_ttl: int = 3600      # Session 历史保留时间 (秒)
#     ):
#         # 全局订阅: event_type -> [handlers]
#         self._global_handlers: Dict[str, List[Callable[[E], Awaitable[None]]]] = defaultdict(list)
        
#         # 活跃通道: session_id -> Set[Queue]
#         # 使用 Set 方便移除，O(1) 复杂度
#         self._active_channels: Dict[str, set[asyncio.Queue]] = defaultdict(set)
        
#         # 历史记录: session_id -> deque[Event]
#         # 使用 deque(maxlen=N) 自动丢弃旧消息，防止单次运行内存爆炸
#         self._history: Dict[str, deque[E]] = defaultdict(lambda: deque(maxlen=history_limit))
        
#         # 简单的 TTL 记录 (实际生产建议使用 Redis，内存版仅做简单清理)
#         self._session_last_active: Dict[str, float] = {}
#         self._ttl = session_ttl

#         # 启动清理任务
#         asyncio.create_task(self._cleanup_loop())

#     async def publish(self, topic: str, event: E, event_type: str = "default"):
#         """
#         发布事件
#         :param topic: 通常是 run_id 或 session_id
#         :param event: 事件对象
#         :param event_type: 用于全局路由的类型标识
#         """
#         # 1. 更新活跃时间
#         self._session_last_active[topic] = time.time()

#         # 2. 存入历史 (Backfill)
#         # deque 会自动处理溢出
#         self._history[topic].append(event)

#         # 3. 广播给活跃的监听者 (Session Broadcast)
#         if topic in self._active_channels:
#             # 复制集合防止迭代时修改
#             for q in list(self._active_channels[topic]):
#                 try:
#                     # 使用 put_nowait，如果满了则丢弃最旧的 (或者打印警告)
#                     # 更好的做法是 Queue 设大一点，或者前端有消费能力检测
#                     q.put_nowait(event)
#                 except asyncio.QueueFull:
#                     logger.warning(f"EventBus queue full for topic {topic}, dropping event.")

#         # 4. 执行全局 Handlers (Fire-and-forget 或 awaitGather)
#         # 为了不阻塞主流程，这里建议使用 create_task 或 gather(return_exceptions=True)
#         handlers = self._global_handlers.get(event_type, [])
#         handlers.extend(self._global_handlers.get("*", []))
        
#         if handlers:
#             # 并发执行所有 Handler，互不阻塞，且不阻塞 publish 本身返回
#             # 注意：这意味着 Handler 的执行是异步的，不保证顺序
#             for handler in handlers:
#                 asyncio.create_task(self._safe_run_handler(handler, event))

#     async def _safe_run_handler(self, handler, event):
#         try:
#             await handler(event)
#         except Exception as e:
#             logger.error(f"EventBus handler failed: {e}", exc_info=True)

#     def listen(self, topic: str) -> asyncio.Queue:
#         """
#         监听指定 Topic，自动回填历史
#         """
#         # 设置合理的缓冲大小
#         q = asyncio.Queue(maxsize=5000)
        
#         # [核心] Backfill: 先把历史塞进去
#         if topic in self._history:
#             for past_event in self._history[topic]:
#                 try:
#                     q.put_nowait(past_event)
#                 except asyncio.QueueFull:
#                     # 历史太长，Queue 太小，只保留最新的历史
#                     # 但由于是从头遍历，这会丢弃最新的。
#                     # 如果历史真的很重要，应该调大 maxsize
#                     logger.warning(f"Backfill queue full for topic {topic}")
#                     break
        
#         self._active_channels[topic].add(q)
#         return q

#     def unlisten(self, topic: str, queue: asyncio.Queue):
#         """取消监听"""
#         if topic in self._active_channels:
#             self._active_channels[topic].discard(queue)
#             if not self._active_channels[topic]:
#                 del self._active_channels[topic]
#                 # 注意：这里只删连接，不删历史 (_history)，等待 TTL 清理

#     async def subscribe(self, event_type: str, handler: Callable[[E], Awaitable[None]]):
#         """全局订阅"""
#         self._global_handlers[event_type].append(handler)

#     async def _cleanup_loop(self):
#         """简单的后台清理任务，防止内存泄漏"""
#         while True:
#             await asyncio.sleep(600) # 每10分钟检查一次
#             try:
#                 now = time.time()
#                 expired_topics = [
#                     topic for topic, last_active in self._session_last_active.items()
#                     if now - last_active > self._ttl
#                 ]
#                 for topic in expired_topics:
#                     if topic not in self._active_channels: # 只有没人听的时候才删
#                         logger.info(f"Cleaning up expired event history for {topic}")
#                         self._history.pop(topic, None)
#                         self._session_last_active.pop(topic, None)
#             except Exception as e:
#                 logger.error(f"EventBus cleanup failed: {e}")

from abc import ABC, abstractmethod
from typing import Set,Dict, TypeVar, Generic,AsyncGenerator
from pydantic import BaseModel
import asyncio
import time
import logging
from collections import defaultdict, deque
from goose.events.types import Event

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



class MemoryEventBus(IEventBus[Event]):
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