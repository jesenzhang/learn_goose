# tests/test_workflow_advanced.py

import asyncio
from src.goose.workflow.graph import Graph
from src.goose.workflow.nodes import FunctionNode, MapNode
from src.goose.workflow.scheduler import WorkflowScheduler
from src.goose.workflow.context import WorkflowContext

async def main():
    graph = Graph()
    
    # 1. 定义工具函数
    def double_num(num, ctx):
        return num * 2
    
    def check_sum(ctx: WorkflowContext) -> str:
        # Router 函数：决定下一步去哪
        total = sum(ctx.get("processed_list", []))
        print(f"🧐 Check Sum: {total}")
        if total > 10:
            return "__END__" # 结束
        else:
            return "add_more" # 进入循环分支

    def add_more_data(ctx: WorkflowContext):
        print("🔄 Sum too low, adding more data...")
        current = ctx.get("input_list", [])
        current.append(5) # 追加数据
        ctx.set("input_list", current)

    # 2. 构建节点
    # Map 节点：并发执行 double_num
    # 输入变量 input_list, 输出变量 processed_list
    mapper = MapNode(FunctionNode(double_num), "input_list", "processed_list")
    graph.add_node("mapper", mapper)
    
    # 修改数据的节点 (Loop 的一部分)
    graph.add_node("add_more", FunctionNode(lambda _, ctx: add_more_data(ctx)))

    # 3. 构建边
    # Start -> Mapper
    graph.set_entry_point("mapper")
    
    # Mapper -> Check (条件边)
    graph.add_conditional_edge("mapper", check_sum)
    
    # AddMore -> Mapper (闭环 Loop)
    graph.add_edge("add_more", "mapper")

    # 4. 运行
    scheduler = WorkflowScheduler(graph)
    
    initial_data = {"input_list": [1, 2]} # sum = 2+4 = 6 (<10)
    
    print("🚀 Starting Advanced Workflow...")
    await scheduler.run(initial_data, run_id="test_adv_1")

if __name__ == "__main__":
    asyncio.run(main())