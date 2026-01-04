import asyncio
import logging
from goose.events.types import SystemEvents, Event
from goose.server.repositories import ExecutionRepository
import goose.globals as G

logger = logging.getLogger("goose.server.listener")

async def sync_execution_status():
    """
    后台任务：监听全局 EventBus，同步状态到 executions 表
    """
    runtime = G.get_runtime()
    if not runtime:
        logger.warning("Runtime not ready, sync listener skipping.")
        return

    repo = ExecutionRepository()
    
    # 监听全局所有 run_id 的事件 (subscribe 参数为 None 或通配符，取决于 Bus 实现)
    # 如果 MemoryBus 支持 subscribe_all() 最好，否则需要稍微改动 Bus 逻辑
    # 假设 bus.subscribe("*") 可以监听所有频道
    
    logger.info("🎧 Starting Execution Status Syncer...")
    
    # 这里演示逻辑：假设我们有一个全局通道或通过某种方式hook了所有事件
    # 在 Goose 的设计中，通常建议 Server 层面维护一个独立的 Listener
    
    async for event in runtime.bus.subscribe_global(): # 假设你给 Bus 加了这个方法
        try:
            if event.type == SystemEvents.WORKFLOW_COMPLETED:
                # event.data 通常包含 outputs
                outputs = event.data.get("outputs", {})
                await repo.update_status(
                    run_id=event.run_id, 
                    status="completed", 
                    outputs=outputs
                )
                logger.info(f"✅ Synced COMPLETED status for {event.run_id}")

            elif event.type == SystemEvents.WORKFLOW_FAILED:
                error = str(event.data.get("error", "Unknown Error"))
                await repo.update_status(
                    run_id=event.run_id, 
                    status="failed", 
                    error=error
                )
                logger.info(f"❌ Synced FAILED status for {event.run_id}")
                
            elif event.type == SystemEvents.WORKFLOW_STARTED:
                await repo.update_status(run_id=event.run_id, status="running")
                
        except Exception as e:
            logger.error(f"Error syncing status for event {event.type}: {e}")