import asyncio
import logging
from goose.component.registry import ComponentRegistry
from goose.component.library import LLMComponent, CodeComponent, StartComponent # 确保这些类被导入以触发注册
from goose.adapter.vueflow import VueFlowAdapter
from goose.workflow.scheduler import WorkflowScheduler
from goose.persistence import SQLiteBackend, PersistenceManager
from goose.session.repository import register_session_schemas
from goose.workflow.repository import register_workflow_schemas

# 配置日志
logging.basicConfig(level=logging.INFO)

async def main():
    # 1. 准备 DB
    pm = PersistenceManager.initialize(SQLiteBackend(":memory:"))
    register_session_schemas()
    register_workflow_schemas()
    await pm.boot()

    # 2. 模拟前端传来的 VueFlow JSON
    vueflow_data = {
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "data": { "label": "User Input", "config": {}, "inputs": {} },
                "position": {"x": 0, "y": 0}
            },
            {
                "id": "llm_1",
                "type": "llm_chat",
                "data": {
                    "label": "AI Writer",
                    "config": { "model": "gpt-3.5", "system_prompt": "You are a poet." },
                    # 引用 start 节点的输入
                    "inputs": { "input": "{{ start_1.topic }}" }
                },
                "position": {"x": 200, "y": 0}
            },
            {
                "id": "code_1",
                "type": "python_code",
                "data": {
                    "label": "Formatter",
                    "config": { 
                        "code": "def main(**k):\n    return f'### POEM ###\\n{k.get(\"text\", \"\")}'" 
                    },
                    # 引用 LLM 节点的输出
                    "inputs": { "text": "{{ llm_1.output }}" }
                },
                "position": {"x": 400, "y": 0}
            }
        ],
        "edges": [
            { "id": "e1", "source": "start_1", "target": "llm_1" },
            { "id": "e2", "source": "llm_1", "target": "code_1" },
            { "id": "e3", "source": "code_1", "target": "__END__" } # 假设前端支持连到特殊的 END
        ]
    }

    # 3. 转换
    adapter = VueFlowAdapter()
    graph = adapter.convert(vueflow_data)
    
    # 4. 执行
    print("\n🚀 Executing VueFlow Graph...")
    scheduler = WorkflowScheduler(graph)
    
    inputs = {"topic": "The Moon"}
    
    async for event in scheduler.run(inputs):
        if event.type == "node_finished":
            print(f"✅ Node {event.node_id} Done -> {str(event.output_data)[:50]}...")
        elif event.type == "workflow_completed":
            print(f"🎉 Final Result: {event.final_output}")

    await pm.shutdown()

if __name__ == "__main__":
    asyncio.run(main())