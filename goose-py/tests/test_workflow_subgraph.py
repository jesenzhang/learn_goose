import asyncio
import os
import sys
import shutil
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from goose.persistence import SQLiteBackend, PersistenceManager
from goose.session.repository import register_session_schemas
from goose.workflow.repository import register_workflow_schemas
from goose.workflow.graph import Graph
from goose.workflow.nodes import FunctionNode
from goose.workflow.subgraph import SubgraphNode
from goose.workflow.scheduler import WorkflowScheduler

logging.basicConfig(level=logging.INFO)

TEST_DB_PATH = "./temp_test_data/subgraph.db"

async def setup_env():
    if os.path.exists("./temp_test_data"):
        shutil.rmtree("./temp_test_data")
    os.makedirs("./temp_test_data", exist_ok=True)

# --- 业务函数 ---
def add_ten(val): return int(val) + 10
def mul_two(val): return int(val) * 2
def format_str(val): return f"Total: {val}"

# --- 构建子图 ---
def build_child_graph() -> Graph:
    g = Graph()
    # input (from parent) -> node_add
    # 子图的 start 节点输出就是父图传进来的 input
    g.add_node("node_add", FunctionNode(
        add_ten, 
        inputs={"val": "{{ start.number }}"} # 引用初始输入
    ))
    
    g.add_node("node_mul", FunctionNode(
        mul_two, 
        inputs={"val": "{{ node_add.output }}"}
    ))
    
    g.add_edge("node_add", "node_mul")
    g.add_edge("node_mul", "__END__")
    g.set_entry_point("node_add")
    return g

async def main():
    await setup_env()
    
    # 1. Init Persistence
    pm = PersistenceManager.initialize(SQLiteBackend(TEST_DB_PATH))
    register_session_schemas()
    register_workflow_schemas()
    await pm.boot()

    # 2. Build Graphs
    child_graph = build_child_graph()
    parent_graph = Graph()

    # Parent Node 1: Subgraph
    # 我们把整个 child_graph 包装成一个节点
    sub_node = SubgraphNode(
        child_graph,
        inputs={"number": "{{ start.initial }}"}, # 映射：父的 initial -> 子的 number
        name="math_subgraph"
    )
    parent_graph.add_node("my_subtask", sub_node)

    # Parent Node 2: Finalize
    # 这里的引用需要注意：SubgraphNode 返回的是子图的 context.node_outputs
    # 所以结构是: { "node_add": {...}, "node_mul": {"output": 40} }
    # 引用路径: {{ my_subtask.node_mul.output }}
    parent_graph.add_node("final_fmt", FunctionNode(
        format_str,
        inputs={"val": "{{ my_subtask.node_mul.output }}"}
    ))

    parent_graph.add_edge("my_subtask", "final_fmt")
    parent_graph.add_edge("final_fmt", "__END__")
    parent_graph.set_entry_point("my_subtask")

    # 3. Run Parent
    scheduler = WorkflowScheduler(parent_graph)
    
    # Input: 10 -> (10+10)*2 = 40 -> "Total: 40"
    initial_data = {"initial": 10}
    
    print("🚀 Running Nested Workflow...")
    
    async for event in scheduler.run(initial_data):
        if event.type == "node_finished":
            print(f"   [Parent] Node {event.node_id} Done -> {event.output_data}")
        elif event.type == "workflow_completed":
            print(f"   🎉 Parent Workflow Done: {event.final_output}")

    # 4. Verify
    # 我们应该能看到 "Total: 40"
    
    await pm.shutdown()

if __name__ == "__main__":
    asyncio.run(main())