from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from goose.system import get_runtime
from goose.workflow.scheduler import WorkflowScheduler

router = APIRouter()

@router.post("/run")
async def start_run(inputs: dict):
    # 触发运行，立刻返回 run_id
    scheduler = WorkflowScheduler()
    run_id = await scheduler.run(inputs) # 假设这是非阻塞的
    return {"run_id": run_id}

@router.get("/stream/{run_id}")
async def stream_run(run_id: str, last_seq_id: int = -1):
    runtime = get_runtime()
    streamer = runtime.create_streamer(run_id)
    
    async def event_generator():
        # Server 端的消费者：转换成 SSE 格式
        async for event in streamer.listen(after_seq_id=last_seq_id):
            yield {
                "event": "message",
                "id": event.seq_id,
                "data": event.model_dump_json()
            }
            # Server 端不需要打印到控制台，而是推给前端

    return EventSourceResponse(event_generator())