import pytest
import asyncio
from goose.events import SystemEvents,MemoryEventBus
from goose.events.persister import SQLStreamPersister
from goose.workflow.streamer import StreamerFactory
from goose.persistence.manager import persistence_manager
from goose.persistence.backend import SQLiteBackend

@pytest.mark.asyncio
async def test_full_streamer_lifecycle():
    # 1. 初始化基础设施
    backend = SQLiteBackend(":memory:")
    persistence_manager.set_backend(backend)
    await persistence_manager.boot()
    
    bus = MemoryEventBus()
    persister = SQLStreamPersister()
    factory = StreamerFactory(bus, persister)
    
    run_id = "test_run_001"
    streamer = factory.create(run_id)
    
    # 2. 模拟前端订阅者 (Consumer)
    received_realtime = []
    
    async def consumer_task():
        async for event in streamer.subscribe():
            received_realtime.append(event)
    
    # 启动监听任务
    listen_task = asyncio.create_task(consumer_task())
    
    # 3. 模拟 Scheduler 发送事件 (Producer)
    await streamer.emit(EventType.WORKFLOW_STARTED, {"input": "hi"})
    await streamer.emit(EventType.NODE_STARTED, {"node": "LLM"}, node_id="n1")
    await streamer.emit(EventType.STREAM_TOKEN, "H", node_id="n1")
    await streamer.emit(EventType.STREAM_TOKEN, "i", node_id="n1")
    await streamer.emit(EventType.WORKFLOW_COMPLETED, {"output": "Hi"})
    
    # 等待异步持久化任务完成 (因为 token 是 create_task 发送的)
    await asyncio.sleep(0.1)
    
    # 关闭流
    await streamer.close()
    await listen_task # 等待消费者退出
    
    # 4. 验证实时接收
    assert len(received_realtime) == 5
    assert received_realtime[0].type == EventType.WORKFLOW_STARTED
    assert received_realtime[2].data == "H"
    assert received_realtime[2].seq_id == 3
    
    # 5. 验证数据库持久化 (History)
    history_events = await persister.get_events(run_id)
    assert len(history_events) == 5
    assert history_events[-1].type == EventType.WORKFLOW_COMPLETED
    
    # 6. 验证 Streamer.history() 接口
    replayed_events = []
    async for evt in streamer.history():
        replayed_events.append(evt)
    assert len(replayed_events) == 5
    assert replayed_events[0].id == received_realtime[0].id
    
    print("\n✅ Event System Test Passed: Realtime + Persistence + History Replay")

if __name__ == "__main__":
    asyncio.run(test_full_streamer_lifecycle())