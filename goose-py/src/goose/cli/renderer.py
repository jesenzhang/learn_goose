import sys
from goose.events import SystemEvents,BaseStreamer

async def console_renderer(streamer:BaseStreamer):
    """
    CLI 专用的消费者：订阅 Streamer 并打印到标准输出
    """
    async for event in streamer.listen():
        if event.type == SystemEvents.STREAM_TOKEN:
            # 流式打印 Token，不换行
            sys.stdout.write(event.data)
            sys.stdout.flush()
        elif event.type == SystemEvents.NODE_STARTED:
            print(f"\n[Step] Node {event.producer_id} started...")
        elif event.type == SystemEvents.WORKFLOW_COMPLETED:
            print(f"\n\n✅ Workflow Finished. Result: {event.data}")
        elif event.type == SystemEvents.WORKFLOW_FAILED:
            print(f"\n\n❌ Error: {event.data}")