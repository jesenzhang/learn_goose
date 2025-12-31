import asyncio
import typer
from goose.system import boot, shutdown, get_runtime
from goose.config import SystemConfig
from goose.workflow.scheduler import WorkflowScheduler
from goose.cli.renderer import console_renderer

app = typer.Typer()

@app.command()
def run(
    query: str, 
    db: str = "sqlite:///:memory:" # CLI 默认用内存库，跑完即焚
):
    """
    CLI Command: Run a workflow
    """
    async def _main():
        # 1. Boot System (CLI Mode)
        config = SystemConfig(DB_URL=db)
        runtime = await boot(config)
        
        try:
            # 2. 准备组件
            run_id = "cli_run_001"
            # 注意：Streamer 是在这里创建的，但 Scheduler 内部也会用到 Bus
            streamer = runtime.create_streamer(run_id)
            scheduler = WorkflowScheduler() 
            
            # 3. 并行执行：任务运行 + 控制台渲染
            # 使用 asyncio.gather 让两者同时跑
            
            # 任务逻辑
            inputs = {"query": query}
            task_run = asyncio.create_task(scheduler.run(inputs, run_id=run_id))
            
            # 渲染逻辑 (监听同一个 run_id 的 Bus)
            task_render = asyncio.create_task(console_renderer(streamer))
            
            await task_run
            # 任务结束后，稍微等一下让剩余日志吐完，或者让 renderer 根据 completed 事件自动退出
            
        finally:
            await shutdown()

    asyncio.run(_main())

if __name__ == "__main__":
    app()