# tests/test_coze_full.py

import asyncio
from goose.workflow.graph import Graph
from goose.workflow.nodes import ToolNode, FunctionNode, MapNode, AgentNode
from goose.workflow.scheduler import WorkflowScheduler
from goose.workflow.conditions import Condition
from goose.tools import Tool, ToolRegistry
from goose.agent import Agent
from goose.conversation import CallToolResult,RawContent
from goose.model import ModelConfig
from goose.providers.openai import OpenAIProvider

# 配置
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"

config = ModelConfig(model_name=MODEL_NAME)
provider = OpenAIProvider(model_config=config, base_url=API_BASE, api_key=API_KEY)


# 1. 定义一个 Mock Tool
class MockSearchTool(Tool):
    name = "search"
    description = "Search engine"
    async def run(self, query: str):
        # 模拟返回 JSON 字符串，实际 ToolNode 会返回 text
        # 这里为了演示方便，假设 Tool 直接返回 Python 对象 (需要修改 ToolNode 支持)
        # 或者我们用 FunctionNode 模拟 Search
        return CallToolResult.success([RawContent(text='["cat1", "cat2", "cat3"]')]).content[0].text

async def main():
    graph = Graph()
    
    # Node 1: 模拟搜索 (这里用 FunctionNode 方便返回 List)
    def search_func(query):
        print(f"🔎 Searching for: {query}")
        return ["cat_A", "cat_B", "cat_C"] if query == "cat" else []
        
    graph.add_node("search", FunctionNode(
        search_func, 
        inputs={"query": "{{ start.topic }}"} # 引用 Start
    ))
    
    # Node 2: 判断结果 (Condition)
    # 我们需要一个中间节点来计算长度吗？Condition 可以直接写 lambda
    # 路由逻辑：检查 {{ search.output }} 的长度
    router = Condition("{{ search.output }}") \
                .if_match(lambda x: len(x) > 0, "process_map") \
                .else_goto("end_fail")
                
    graph.add_conditional_edge("search", router)
    
    # Branch A: Map 处理
    # 子节点：大写化
    def upper_func(text):
        return f"PROCESSED_{text}"
        
    process_node = MapNode(
        node=FunctionNode(upper_func, inputs={"text": "{{ item }}"}), # 引用 Item
        inputs={"list": "{{ search.output }}"} # 引用 Search 结果
    )
    graph.add_node("process_map", process_node)
    
    # Branch B: 失败节点
    fail_agent = Agent("FailBot", provider)
    graph.add_node("end_fail", AgentNode(fail_agent, inputs={"input": "Say sorry."}))
    
    # Map 结束后去哪？假设结束
    graph.add_edge("process_map", "__END__")
    
    graph.set_entry_point("search")
    
    # Run
    scheduler = WorkflowScheduler(graph)
    print("🚀 Running Coze Workflow...")
    
    async for event in scheduler.run({"topic": "cat"}, "coze_full_1"):
        if event.type == "node_finished":
            print(f"✅ {event.node_id} -> {event.output_data}")

if __name__ == "__main__":
    asyncio.run(main())