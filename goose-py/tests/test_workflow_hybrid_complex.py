import asyncio
import os
import sys
import shutil
import logging
from typing import Dict, Any

# --- 路径设置 ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.goose.persistence import SQLiteBackend, PersistenceManager
from src.goose.session.repository import register_session_schemas
from src.goose.workflow.repository import register_workflow_schemas, WorkflowRepository
from src.goose.workflow.graph import Graph
from src.goose.workflow.nodes import FunctionNode
from src.goose.workflow.scheduler import WorkflowScheduler
from src.goose.workflow.context import WorkflowContext

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_hybrid")

TEST_DB_PATH = "./temp_test_data/hybrid_workflow.db"

async def setup_env():
    if os.path.exists("./temp_test_data"):
        shutil.rmtree("./temp_test_data")
    os.makedirs("./temp_test_data", exist_ok=True)

# --- 1. 定义业务函数 ---

def add_ten(current_val: int):
    """
    纯函数：加10
    """
    res = int(current_val) + 10
    logger.info(f"🧮 Calculator: {current_val} + 10 = {res}")
    return res

def format_result(val: int):
    """
    纯函数：格式化
    """
    return f"🎉 Final Result is {val}!"

# --- 2. 定义混合风格的 Router ---

def check_value_router(ctx: WorkflowContext) -> str:
    """
    LangGraph 风格的 Router (Python 代码控制逻辑)
    +
    Coze 风格的数据获取 (通过 Context 获取节点输出)
    """
    # 获取 'adder_node' 的输出
    # 注意：第一次进入循环时，adder_node 还没运行，可能需要回退获取 'start' 的输入
    
    # 策略：优先看 adder 的输出，如果没有（第一次运行），看 start 的输入
    last_val = ctx.get_node_output("adder_node", "output")
    if last_val is None:
        # 第一次运行，router 不会被调用，因为边是 adder -> router
        # 但如果是 conditional entry point 可能会用到
        pass

    logger.info(f"🚦 Router checking value: {last_val}")
    
    if last_val < 30:
        return "adder_node"  # Loop: 回到加法节点
    else:
        return "final_node"  # End: 结束

# --- 测试主逻辑 ---

async def main():
    await setup_env()
    print("🚀 Starting Hybrid Workflow Test (Loop + Condition + Persistence)...\n")

    # 1. 初始化持久层
    backend = SQLiteBackend(TEST_DB_PATH)
    pm = PersistenceManager.initialize(backend)
    register_session_schemas()
    register_workflow_schemas()
    await pm.boot()

    # 2. 构建图
    graph = Graph()

    # Node A: 加法器
    # [Coze Style] 输入参数映射
    # 这里有个难点：Loop 中参数来源会变。
    # 第一次来源是 {{ start.initial_value }}
    # 后续来源是 {{ adder_node.output }}
    # 
    # 解决方案：
    # 1. 在 Router 里做数据规整 (把结果写回 context 的公共区域)
    # 2. 或者使用 Python 函数的动态特性，我们在 FunctionNode 内部处理这个逻辑
    # 3. 或者使用类似 LangGraph 的 State 更新机制 (State 是全局的)
    # 
    # 为了演示 goose-py 当前的 Context 能力，我们采用一种"优先取值"的策略
    # 或者我们简单点：让 FunctionNode 接收两个参数，哪个有值用哪个
    
    def smart_add(start_val, loop_val):
        # 优先用 loop_val (上一轮计算结果)，没有则用 start_val
        val = loop_val if loop_val is not None else start_val
        return add_ten(val)

    graph.add_node("adder_node", FunctionNode(
        smart_add,
        inputs={
            "start_val": "{{ start.initial_value }}",
            "loop_val": "{{ adder_node.output }}" # 引用自己上一轮的输出
        }
    ))

    # Node B: 结束节点
    graph.add_node("final_node", FunctionNode(
        format_result,
        inputs={"val": "{{ adder_node.output }}"}
    ))

    # Edges (LangGraph Style)
    # 1. Start -> Adder
    graph.set_entry_point("adder_node")
    
    # 2. Adder -> Router (Conditional)
    graph.add_conditional_edge("adder_node", check_value_router)
    
    # 3. Router -> Final (隐式：check_value_router 返回 "final_node")
    
    # 4. Final -> End
    graph.add_edge("final_node", "__END__")

    # 3. 运行
    scheduler = WorkflowScheduler(graph)
    
    print("▶️ Running Loop Workflow...")
    # 初始值 0 -> 10 -> 20 -> 30 (Stop)
    initial_input = {"initial_value": 0} 
    
    run_id = None
    node_history = []

    async for event in scheduler.run(initial_input):
        if event.type == "workflow_started":
            run_id = event.session_id
            print(f"   🔹 Session: {run_id}")
        elif event.type == "node_finished":
            node_history.append(event.node_id)
            print(f"   ✅ Node Finished: {event.node_id} -> {event.output_data}")

    # 4. 验证逻辑
    print("\n🔍 Verifying Execution Logic...")
    
    # 预期路径: adder -> adder -> adder -> final
    # 0->10 (Loop), 10->20 (Loop), 20->30 (Exit), 30 -> Format
    print(f"   Path Taken: {node_history}")
    
    assert node_history.count("adder_node") == 3, "Should loop 3 times (0->10, 10->20, 20->30)"
    assert node_history[-1] == "final_node", "Should end at final node"

    # 5. 验证持久化
    print("\n🔍 Verifying Persistence...")
    repo = WorkflowRepository()
    state = await repo.load_checkpoint(run_id)
    
    print(f"   Final Status: {state.status}")
    print(f"   Final Context Keys: {list(state.context_data.keys())}")
    
    # 检查 adder_node 最后一次的输出是否为 30
    final_adder_val = state.context_data["adder_node"]["output"]
    assert final_adder_val == 30
    
    await PersistenceManager.get_instance().shutdown()
    print("\n✅ Hybrid Workflow Test Passed!")

if __name__ == "__main__":
    asyncio.run(main())