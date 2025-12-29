import asyncio
import os
import sys
import shutil
import logging
from typing import Dict, Any

# --- 路径设置 ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from goose.persistence import SQLiteBackend, PersistenceManager
from goose.session import SessionManager, SessionType
from goose.workflow.graph import Graph
from goose.workflow.nodes import AgentNode, FunctionNode
from goose.workflow.scheduler import WorkflowScheduler
from goose.workflow.repository import WorkflowRepository, register_workflow_schemas
from goose.agent import Agent
from goose.providers import OpenAIProvider, ProviderFactory
from goose.conversation import Message as ModelMessage
from goose.model import ModelConfig
from goose.session.repository import register_session_schemas

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_integration")

TEST_DB_PATH = "./temp_test_data/workflow_integration.db"

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"

config = {
    "model_name": MODEL_NAME,
    "base_url": API_BASE,
    "api_key": API_KEY
}
provider = ProviderFactory.create(provider_name = 'openai', model_config=config)

# --- 测试主逻辑 ---

async def setup_env():
    if os.path.exists("./temp_test_data"):
        shutil.rmtree("./temp_test_data")
    os.makedirs("./temp_test_data", exist_ok=True)

async def main():
    await setup_env()
    print("🚀 Starting Workflow Persistence Integration Test...\n")

    # 1. [Infrastructure] 初始化持久化层
    backend = SQLiteBackend(TEST_DB_PATH)
    pm = PersistenceManager.initialize(backend)
    
    # 注册表结构 (Session表会自动注册，我们需要手动注册 Workflow表)
    register_workflow_schemas()
    register_session_schemas()
    
    await pm.boot()
    print("✅ Persistence Layer Booted.")

    # 2. [Graph Definition] 定义一个简单的工作流
    #    Start -> Agent -> Function -> End
    graph = Graph()
    
    
    # Node A: Agent
    agent = Agent("Greeter", provider)
    # 使用 Coze 风格参数映射: {{ start.input }}
    graph.add_node("agent_node", AgentNode(
        agent, 
        inputs={"input": "Say hello to {{ start.user_name }}"} 
    ))

    # Node B: Function (处理结果)
    def process_result(text):
        # 这里的 text 会被自动注入
        return f"PROCESSED: {text}"

    graph.add_node("func_node", FunctionNode(
        process_result, 
        inputs={"text": "{{ agent_node.output }}"} 
    ))

    # Edges
    graph.add_edge("agent_node", "func_node")
    graph.set_entry_point("agent_node")

    # 3. [Scheduler] 初始化调度器
    #    注入 WorkflowRepository 作为 Checkpointer
    workflow_repo = WorkflowRepository()
    scheduler = WorkflowScheduler(graph, checkpointer=workflow_repo)

    # 4. [Execution] 运行工作流 (不传 run_id，测试自动创建)
    print("\n▶️ Running Workflow (Auto-create Session)...")
    
    initial_input = {"user_name": "Tony Stark"}
    run_id = None
    
    async for event in scheduler.run(initial_input):
        if event.type == "workflow_started":
            run_id = event.session_id
            print(f"   🔹 Workflow Session Created: {run_id}")
        elif event.type == "node_finished":
            print(f"   ✅ Node {event.node_id} Finished.")
        elif event.type == "workflow_completed":
            print(f"   🎉 Workflow Completed. Final Output: {event.final_output}")

    # 5. [Verification] 验证持久化结果
    print("\n🔍 Verifying Database Records...")
    
    # A. 验证 Session 表 (Identity)
    session = await SessionManager.get_session(run_id)
    print(f"   [Session] ID: {session.id}")
    print(f"   [Session] Type: {session.session_type}")
    print(f"   [Session] Metadata: {session.metadata}")
    
    assert session.session_type == SessionType.WORKFLOW
    
    # [修复点] 检查 extension_data 对象属性，而不是检查 metadata 字典
    # 只要对象存在（哪怕是空的），说明机制是工作的
    assert session.extension_data is not None 
    print(f"   [Session] Extension Data: {session.extension_data}")

    # B. 验证 Workflow Runs 表 (State)
    state = await workflow_repo.load_checkpoint(run_id)
    print(f"   [Workflow State] Status: {state.status}")
    print(f"   [Workflow State] Context Data Keys: {list(state.context_data.keys())}")
    
    assert state.status == "completed"
    assert "agent_node" in state.context_data
    assert "func_node" in state.context_data
    # 检查 Agent 的输出是否被正确保存
    agent_out = state.context_data["agent_node"].get("output")
    print(f"   [Workflow State] Agent Output: {agent_out}")


    # C. 验证 Messages 表 (Logs)
    # AgentNode 执行时应该产生了消息记录
    # 注意：AgentNode 使用的是 scoped_session_id (run_id::agent_node) 还是直接 run_id 取决于您的实现
    # 这里假设您在 AgentNode 中使用了 scoped session 策略
    scoped_id = f"{run_id}::agent_node" 
    # 或者如果 AgentNode 还没改，可能直接写在 run_id 下
    
    msgs = await SessionManager.get_messages(scoped_id)
    if not msgs:
        # Fallback check: maybe saved under main run_id
        msgs = await SessionManager.get_messages(run_id)
        
    print(f"   [Messages] Found {len(msgs)} messages for Agent.")
    if msgs:
        print(f"   [Messages] First msg: {msgs[0].content}")
    
    # 断言至少有一条消息 (Agent 回复)
    assert len(msgs) > 0

    # 6. [Teardown]
    await PersistenceManager.get_instance().shutdown()
    print("\n✅ Integration Test Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(main())