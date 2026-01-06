import asyncio
import json
import logging
import sys
import os
import uuid
from pathlib import Path
from typing import Dict, Any, List

from goose.workflow.converter import WorkflowConverter

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

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IntegrationTest")

# ==========================================
# 0. 测试数据准备 (Test Data Setup)
# ==========================================

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

# ==========================================
# 3. 渲染客户端 (Console Client)
# ==========================================

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

# ==========================================
# 4. 主程序
# ==========================================

async def main():
    # --- Step 0: 准备文件 ---
   
    
# --- Step 1: 系统启动 (Boot) ---
    logger.info("⚡ Booting System...")
    
    config = SystemConfig()
    # boot() 会负责初始化 Runtime, Persistence, Resources
    runtime = await boot(config)
    workflow = ensure_test_json_exists()
    # --- Step 2: 加载图 ---
    logger.info(f"📂 Loading workflow from {TEST_JSON_PATH}...")
    try:
        converter = WorkflowConverter()
        graph = converter.convert(workflow)
        logger.info(f"   Graph loaded: {len(graph.nodes)} nodes configured.")
    except Exception as e:
        logger.error(f"Failed to load graph: {e}")
        return

    # --- Step 3: 运行工作流 (实时) ---
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    scheduler = WorkflowScheduler()
    client = ConsoleClient(run_id)
    
    logger.info(f"▶️ Starting Execution [RunID: {run_id}]")
    
    # 并行执行：调度器跑任务 vs 客户端看直播
    await asyncio.gather(
        scheduler.run(graph, inputs={"query": "Manual Trigger"}, run_id=run_id),
        client.connect(client_name="Live_Viewer")
    )
    
    # --- Step 4: 测试挂起与恢复 (Backfill) ---
    logger.info("\n\n🔄 Testing Resume / Backfill Capability...")
    logger.info("   Simulating a new client requesting full history...")
    
    # 模拟新客户端连接，请求 seq_id > -1 (即从头开始)
    client_replay = ConsoleClient(run_id)
    await client_replay.connect(after_seq_id=-1, client_name="History_Viewer")
    
    # --- Step 5: 验证数据一致性 ---
    logger.info("\n📊 Verifying Data Persistence...")
    # 直接从 EventStore 查库
    events = await runtime.event_store.get_events(run_id)
    logger.info(f"   Total events persisted in DB: {len(events)}")
    
    if len(events) == 0:
        logger.error("❌ Persistence failed! No events found.")
        sys.exit(1)
    
    # --- Step 6: 清理 ---
    await shutdown()

    logger.info("✨ Test Finished Successfully.")

if __name__ == "__main__":
    asyncio.run(main())