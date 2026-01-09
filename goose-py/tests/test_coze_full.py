import asyncio
import os
import sys
import shutil
import logging
import json
from typing import Dict, Any, List

# --- 1. 环境配置 ---
# 确保能导入 goose 包
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 核心依赖
from goose.persistence import SQLiteBackend, PersistenceManager
from goose.session import SessionManager
from goose.workflow.graph import Graph
from goose.workflow.scheduler import WorkflowScheduler
from goose.workflow.repository import WorkflowRepository, register_workflow_schemas
from goose.session.repository import register_session_schemas
from goose.components.registry import component_registry

# 组件依赖
from goose.components.buildins.llm import LLMComponent, LLMConfig, OutputDefinition
from goose.components.buildins.code import CodeRunner, CodeConfig, InputMapping
from goose.components.buildins.control import SelectorComponent, SelectorConfig, ConditionBranch
from goose.components.buildins.basic import StartComponent,EndComponent,StartConfig,EndConfig
from goose.providers.base import BaseLLM,ProviderUsage,ProviderFactory
from goose.conversation import Message

# 日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_coze_full")

TEST_DB_PATH = "./temp_test_data/coze_full_workflow.db"



# 为了不修改源码，我们这里使用 unittest.mock 来 patch ProviderFactory
from unittest.mock import patch

# ==========================================
# 3. 编排工作流 (Graph Construction)
# ==========================================

def build_sentiment_graph() -> Graph:
    graph = Graph()

    # --- Node 1: Start (FunctionNode) ---
    # 作用：透传用户输入，作为 Workflow 的入口
    graph.add_node("start_node", StartComponent())

    # --- Node 2: LLM (LLMComponent) ---
    # 作用：分析情感并打分
    llm_config = LLMConfig(
        model="mock-gpt",
        prompt="Analyze sentiment: {{ start_node.user_text }}",
        response_format="json_object",
        output_definitions=[
            OutputDefinition(name="score", type="number", description="Sentiment score (0-100)"),
            OutputDefinition(name="reason", type="string", description="Reasoning")
        ]
    )
    
    # 实例化组件并绑定配置
    llm_comp = LLMComponent()
    llm_comp.config = llm_config.model_dump() # 模拟 Converter 的行为
    
    # 绑定输入映射: input_text 来自 start_node
    # 注意：我们之前约定 Scheduler 会读取 getattr(node, "inputs")
    setattr(llm_comp, "inputs", {"user_text": "{{ start_node.user_text }}"})
    
    graph.add_node("llm_node", llm_comp)

    # --- Node 3: Code (CodeRunner) ---
    # 作用：处理 JSON 数据 (虽然 LLM 已经输出了 JSON，这里演示 Code 组件的数据处理能力)
    code_config = CodeConfig(
        code="""
def main(args):
    score = args.get('score', 0)
    # 简单的业务逻辑：归一化或加权
    final_score = int(score)
    return {"final_score": final_score, "status": "processed"}
""",
        input_parameters=[
            InputMapping(name="score", value="{{ llm_node.score }}")
        ]
    )
    code_comp = CodeRunner()
    code_comp.config = code_config.model_dump()
    # CodeRunner 的 inputs 通常是空的，因为 input_parameters 负责了映射，
    # 但为了触发 TemplateRenderer，我们需要传递上下文。
    # 实际上 CodeRunner.execute 内部会解析 input_parameters。
    setattr(code_comp, "inputs", {}) 
    graph.add_node("code_node", code_comp)

    # --- Node 4: Switch (SelectorComponent) ---
    # 作用：路由分发
    switch_config = SelectorConfig(
        conditions=[
            # 如果分数 > 60，走 "high_score" 句柄
            ConditionBranch(expression="{{ score > 60 }}", target_handle="high_score"),
        ],
        default_handle="low_score"
    )
    switch_comp = SelectorComponent()
    switch_comp.config = switch_config.model_dump()
    # 注入变量供表达式使用
    setattr(switch_comp, "inputs", {"score": "{{ code_node.final_score }}"})
    graph.add_node("switch_node", switch_comp)

    # --- Node 5: End Positive ---
    graph.add_node("end_happy", FunctionNode(
        func=lambda **k: {"result": "😊 Positive Vibe!", "details": k},
        name="End Happy"
    ))
    # 输入映射：接收 Code 的处理结果
    graph.nodes["end_happy"].inputs = {"data": "{{ code_node.final_score }}"}

    # --- Node 6: End Negative ---
    graph.add_node("end_sad", FunctionNode(
        func=lambda **k: {"result": "😔 Needs Improvement", "details": k},
        name="End Sad"
    ))
    graph.nodes["end_sad"].inputs = {"data": "{{ code_node.final_score }}"}


    # --- Wiring (连线) ---
    
    # 1. 线性流
    graph.add_edge("start_node", "llm_node")
    graph.add_edge("llm_node", "code_node")
    graph.add_edge("code_node", "switch_node")

    # 2. 条件分支流 (Switch 输出)
    # 句柄 "high_score" -> Happy
    graph.add_edge("switch_node", "end_happy", source_handle="high_score")
    # 句柄 "low_score" -> Sad
    graph.add_edge("switch_node", "end_sad", source_handle="low_score")

    graph.set_entry_point("start_node")
    
    return graph

# ==========================================
# 4. 测试主程序
# ==========================================

async def setup_env():
    if os.path.exists("./temp_test_data"):
        shutil.rmtree("./temp_test_data")
    os.makedirs("./temp_test_data", exist_ok=True)
    print("🧹 Environment cleaned.")

async def main():
    await setup_env()
    print("\n🚀 Starting Coze-like Full Workflow Test...\n")

    # 1. 初始化持久层
    backend = SQLiteBackend(TEST_DB_PATH)
    pm = PersistenceManager.initialize(backend)
    register_workflow_schemas()
    register_session_schemas()
    await pm.boot()

    # 2. 构建图
    graph = build_sentiment_graph()
    
    # 3. 初始化调度器
    repo = WorkflowRepository()
    scheduler = WorkflowScheduler(graph, checkpointer=repo)

    # --- 场景 A: 高分情况 (Mock Score = 85) ---
    print("\n🎬 [Scenario A] Testing Positive Flow (Score=85)...")
    
    mock_high = MockLLMProvider({"score": 85, "reason": "Very happy text"})
    
    # 使用 Patch 拦截 ProviderFactory.create，返回我们的 Mock Provider
    with patch("goose.providers.factory.ProviderFactory.create", return_value=mock_high):
        
        input_data = {"user_text": "I love coding with Goose!"}
        run_id_a = None
        
        async for event in scheduler.run(input_data):
            if event.type == "workflow_started":
                run_id_a = event.session_id
                print(f"   🔹 Session Started: {run_id_a}")
            elif event.type == "node_finished":
                # 显示简略日志
                out_str = str(event.output_data)[:50] + "..." if event.output_data else "None"
                print(f"   ✅ Node [{event.node_id}] -> {out_str}")
            elif event.type == "workflow_completed":
                print(f"   🎉 Workflow Completed: {event.final_output}")
                
                # 断言结果
                assert event.final_output["result"] == "😊 Positive Vibe!"
                print("   ✅ Assertion Passed: Correctly routed to Happy End.")

        # 验证数据库状态
        state = await repo.load_checkpoint(run_id_a)
        assert state.status == "completed"
        # 验证队列是否清空 (新特性验证)
        assert isinstance(state.execution_queue, list)
        assert len(state.execution_queue) == 0
        print("   ✅ DB Persistence Verified.")


    # --- 场景 B: 低分情况 (Mock Score = 40) ---
    print("\n🎬 [Scenario B] Testing Negative Flow (Score=40)...")
    
    mock_low = MockLLMProvider({"score": 40, "reason": "Sad text"})
    
    with patch("goose.providers.factory.ProviderFactory.create", return_value=mock_low):
        
        input_data = {"user_text": "Debugging is frustrating."}
        
        async for event in scheduler.run(input_data):
            if event.type == "workflow_completed":
                print(f"   🎉 Workflow Completed: {event.final_output}")
                
                # 断言结果
                assert event.final_output["result"] == "😔 Needs Improvement"
                print("   ✅ Assertion Passed: Correctly routed to Sad End.")

    # 清理
    await PersistenceManager.get_instance().shutdown()
    print("\n✨ All Full-Workflow Scenarios Passed!")

if __name__ == "__main__":
    asyncio.run(main())