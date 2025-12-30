import asyncio
import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel

# 导入 Goose 核心模块
from goose.registry import sys_registry
from goose.components.base import Component
from goose.components import register_component
from goose.workflow.scheduler import WorkflowScheduler
from goose.adapter.vueflow import VueFlowAdapter
from goose.workflow.converter import WorkflowConverter

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_real_flow")

# ==========================================
# 1. 准备真实的 VueFlow JSON 数据
# ==========================================
# 这是你提供的 test.json 内容
REAL_JSON_DATA = {
  "nodes": [
    {
      "id": "100001",
      "type": "customInput",
      "data": {
        "outputs": [
          {
            "name": "query",
            "type": "string",
            "description": "",
            "defaultValue": ""
          }
        ],
        "nodeMeta": { "title": "开始" }
      }
    },
    {
      "id": "100002",
      "type": "customOutput",
      "data": {
        "inputs": [
          {
            "name": "out",
            "type": "string",
            "source": {
              "sourceId": "7dac3530-7b41-4911-ae31-5f54917dbdda",
              "sourceName": "7dac3530-7b41-4911-ae31-5f54917dbdda.result"
            }
          }
        ],
        "nodeMeta": { "title": "结束" }
      }
    },
    {
      "id": "7dac3530-7b41-4911-ae31-5f54917dbdda",
      "type": "llm",
      "data": {
        "model": { "modelName": "Qwen/Qwen2.5-7B", "temperature": 0.8 },
        "inputs": [
          {
            "name": "query",
            "type": "string",
            "source": { "sourceId": "100001", "sourceName": "100001.query" }
          }
        ],
        "outputs": [
          { "name": "result", "type": "string" }
        ],
        "pluginList": [
          { "id": "searxng_search", "name": "SearXNG Search" }
        ],
        "userPrompt": "回答用户问题：{{query}}",
        "systemPrompt": "你是一个有用的助手"
      }
    }
  ],
  "edges": [
    {
      "id": "e7dac3530-100002",
      "source": "7dac3530-7b41-4911-ae31-5f54917dbdda",
      "target": "100002"
    },
    {
      "id": "e100001-7dac3530",
      "source": "100001",
      "target": "7dac3530-7b41-4911-ae31-5f54917dbdda"
    }
  ]
}
from goose.persistence import SQLiteBackend,persistence_manager
from goose.session.repository import register_session_schemas
from goose.workflow import register_workflow_schemas
# ==========================================
# 3. 执行测试流程
# ==========================================
TEST_DB_PATH = "./temp_test_data/coze_full_workflow.db"
async def run_test():
    # 1. 初始化持久层
    print(f"🕵️ Test Script PM ID: {id(persistence_manager)}")
    backend = SQLiteBackend(TEST_DB_PATH)
    persistence_manager.set_backend(backend)
    register_session_schemas()
    register_workflow_schemas()
    
    await persistence_manager.boot()
    
    
    from goose.session.repository import SessionRepository
    temp_repo = SessionRepository()
    # 2. 打印 Repository 中 PM 的身份证号
    print(f"🕵️ Repo Internal PM ID: {id(temp_repo.backend)}")
    
    
    print("\n🚀 Starting Real-JSON Workflow Test...\n")

    # Step 1: Adapter (JSON -> WorkflowDefinition)
    print("1️⃣  Running VueFlowAdapter...")
    adapter = VueFlowAdapter()
    wf_def = adapter.transform_workflow(REAL_JSON_DATA)
    
    # 打印一下转换后的节点信息，确认 Schema 提取是否成功
    entry_node = next(n for n in wf_def.nodes if n.type == "Entry")
    print(f"   ✅ Entry Node Config: {json.dumps(entry_node.config, ensure_ascii=False)}")
    
    llm_node = next(n for n in wf_def.nodes if n.type == "LLM")
    print(f"   ✅ LLM Node Inputs: {llm_node.inputs}")

    # Step 2: Converter (WorkflowDefinition -> Graph)
    print("\n2️⃣  Running WorkflowConverter...")
    converter = WorkflowConverter()
    graph = converter.convert(wf_def)
    print(f"   ✅ Graph created successfully. Entry point: {graph.entry_point}")

    # Step 3: Scheduler (Execution)
    print("\n3️⃣  Running Scheduler...")
    scheduler = WorkflowScheduler(graph)
    
    # 模拟用户输入
    user_input = {"query": "Goose 架构设计的优势是什么？"}
    
    final_result = None
    async for event in scheduler.run(user_input):
        if event.type == "node_finished":
            print(f"   👉 Node [{event.node_id}] finished.")
        elif event.type == "workflow_completed":
            final_result = event.final_output
            print(f"   🎉 Workflow Completed!")

    # Step 4: Verification
    print("\n4️⃣  Result Verification:")
    print(f"   Input: {user_input}")
    print(f"   Output: {final_result}")
    
    # 验证输出是否包含 Mock LLM 的特征字符串
    expected_part = "模拟回复"
    assert "out" in final_result
    assert expected_part in final_result["out"]
    
    print("\n✅ All tests passed! The pipeline is working correctly.")

if __name__ == "__main__":
    asyncio.run(run_test())