import asyncio
import json
import logging
import sys
import os
import uuid
from pathlib import Path
from typing import Dict, Any, List


# --- 添加 src 到 python path 以便导入 goose 模块 ---
sys.path.append(str(Path(__file__).parent.parent / "src"))

# --- Goose 模块导入 ---
from goose import workflow
from goose.system_config import SystemConfig
from goose.events import IStreamer
from goose.events.types import SystemEvents, Event
from goose.workflow.scheduler import WorkflowScheduler, Graph
from goose.resources.types import ResourceKind
from goose.system import boot, shutdown
from goose.globals import get_streamer_factory, get_runtime
from goose.adapter import AdapterManager
from goose.engine import GooseEngine
from goose.workflow.converter import WorkflowConverter

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IntegrationTest")

TEST_JSON_PATH = Path(r"goose-py/tests/test.json")

def ensure_test_json_exists():
    """
    如果测试文件不存在，创建一个标准的 VueFlow 格式 JSON。
    包含：开始节点 -> LLM节点 (引用系统资源) -> 结束节点
    """

    logger.info(f"Creating default test file at: {TEST_JSON_PATH}")
    TEST_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    
    with open(TEST_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Test file created successfully: {TEST_JSON_PATH}")

    adapter = AdapterManager.get_adapter('vueflow')
    return adapter.transform_workflow(data)


class ConsoleClient:
    """模拟前端 SSE 接收端"""
    def __init__(self, run_id: str):
        self.run_id = run_id
        # 通过全局 Helper 获取工厂
        self.factory = get_streamer_factory()

    async def connect(self, after_seq_id: int = -1, client_name: str = "Client"):
        streamer = self.factory.create(self.run_id)
        logger.info(f"📡 {client_name} connecting to stream (seq > {after_seq_id})...")
        
        buffer = ""
        
        async for event in streamer.listen(after_seq_id=after_seq_id):
            # 处理 Token (不换行打印)
            if event.type == SystemEvents.STREAM_TOKEN:
                sys.stdout.write(f"\033[96m{event.data}\033[0m")
                sys.stdout.flush()
                buffer += str(event.data)
            
            # 处理结构化日志
            elif event.type == SystemEvents.NODE_STARTED:
                print(f"\n[🟢 Node Start] {event.producer_id}")
            
            elif event.type == SystemEvents.NODE_FINISHED:
                print(f"\n[🔴 Node End] {event.producer_id}")
                
            elif event.type == "log":
                print(f"\n[📝 Log] {event.data}")
                
            elif event.type == SystemEvents.WORKFLOW_COMPLETED:
                print(f"\n\n✅ {client_name} Received WORKFLOW_COMPLETED")
                break
                
            elif event.type == SystemEvents.WORKFLOW_FAILED:
                print(f"\n❌ {client_name} Received WORKFLOW_FAILED: {event.data}")
                break


async def main():
    # --- Step 0: 准备 ---
    workflow_def = ensure_test_json_exists()
    
    # --- Step 1: 使用上下文管理器启动系统 ---
    # 只要离开这个缩进块，系统就会自动 shutdown，哪怕中间报错
    async with GooseEngine() as runtime:
        
        # --- Step 2: 加载图 ---
        logger.info(f"📂 Loading workflow from {TEST_JSON_PATH}...")
        converter = WorkflowConverter()
        graph = converter.convert(workflow_def)
        
        # --- Step 3: 运行 ---
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        scheduler = WorkflowScheduler() # Scheduler 内部会通过 G.get_runtime() 获取上下文
        
        client = ConsoleClient(run_id)
        
        logger.info(f"▶️ Starting Execution [RunID: {run_id}]")
        
        await asyncio.gather(
            scheduler.run(graph, inputs={"query": "什么是人工智能"}, run_id=run_id),
            client.connect(client_name="Live_Viewer")
        )
        
        # --- Step 4: Backfill 测试 ---
        logger.info("\n🔄 Testing Resume / Backfill...")
        client_replay = ConsoleClient(run_id)
        await client_replay.connect(after_seq_id=-1, client_name="History_Viewer")
        
        # --- Step 5: 验证持久化 ---
        events = await runtime.event_store.get_events(run_id)
        logger.info(f"📊 Persisted events: {len(events)}")
        
        if len(events) == 0:
            logger.error("❌ Persistence failed!")
    
     
            
    logger.info("✨ Test Finished.")

if __name__ == "__main__":
    asyncio.run(main())