import asyncio
import logging
import json
import sys
import os
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock

# --- 环境设置 ---
# 确保能导入 goose 包
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 导入 Goose 组件
from goose.core.tool import ToolDefinitionRegistry, ToolDefinition, ToolSourceType
from goose.workflow.context import WorkflowContext
from goose.component.code import CodeRunner, CodeConfig, InputMapping
from goose.component.http import HttpRequester, HttpConfig
from goose.component.control import SelectorComponent, SelectorConfig, ConditionBranch, LoopComponent, LoopConfig
from goose.component.plugin import PluginComponent, PluginConfig, ApiParam
from goose.workflow.protocol import WorkflowDefinition

# 配置日志
logging.basicConfig(level=logging.ERROR) # 只显示错误，保持输出清爽

# ==========================================
# 辅助函数
# ==========================================

def create_mock_context() -> WorkflowContext:
    """创建一个带有 Mock Executor 的上下文"""
    ctx = WorkflowContext(session_id="test_session")
    
    # Mock Scheduler (Executor)
    # 模拟 run_to_completion 方法
    mock_executor = MagicMock()
    # 默认返回空，具体测试中会 override side_effect
    mock_executor.run_to_completion = AsyncMock(return_value={})
    
    ctx.set_services(executor=mock_executor)
    return ctx

async def run_test(name: str, coro):
    """运行单个测试并打印结果"""
    print(f"🔄 Testing: {name} ...", end="", flush=True)
    try:
        await coro
        print(" ✅ PASS")
    except AssertionError as e:
        print(f" ❌ FAIL")
        print(f"    AssertionError: {e}")
    except Exception as e:
        print(f" ❌ ERROR")
        print(f"    {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

# ==========================================
# 1. CodeRunner 测试
# ==========================================

async def test_code_runner():
    ctx = create_mock_context()
    
    # 场景: 计算并在返回的消息中引用变量
    config = CodeConfig(
        code="""
def main(args):
    result = args['x'] * args['y']
    return {"val": result, "text": f"Result is {result}"}
""",
        input_parameters=[
            InputMapping(name="x", value=10),
            InputMapping(name="y", value="{{ input_y }}") # 测试模板渲染
        ]
    )
    
    runner = CodeRunner()
    inputs = {"input_y": 5}
    
    # 执行
    res = await runner.invoke(inputs, ctx, config_override=config)
    
    # 断言
    assert res["val"] == 50
    assert res["text"] == "Result is 50"

# ==========================================
# 2. HttpRequester 测试
# ==========================================

async def test_http_requester():
    import respx
    import httpx
    
    ctx = create_mock_context()
    
    # 使用 respx 作为上下文管理器来拦截请求
    with respx.mock(base_url="https://api.test.com") as respx_mock:
        # Mock 定义
        route = respx_mock.post("/users").mock(
            return_value=httpx.Response(201, json={"id": 999, "status": "ok"})
        )
        
        config = HttpConfig(
            method="POST",
            url="https://api.test.com/{{ endpoint }}",
            headers={"X-Auth": "{{ token }}"},
            body_type="json",
            body='{"user": "{{ name }}"}'
        )
        
        runner = HttpRequester()
        inputs = {
            "endpoint": "users", 
            "token": "12345", 
            "name": "Alice"
        }
        
        # 执行
        res = await runner.invoke(inputs, ctx, config_override=config)
        
        # 断言结果
        assert res["status_code"] == 201
        assert res["body"]["id"] == 999
        
        # 断言请求参数是否正确渲染
        last_request = route.calls.last.request
        assert last_request.headers["X-Auth"] == "12345"
        assert json.loads(last_request.content)["user"] == "Alice"

# ==========================================
# 3. Selector (Switch) 测试
# ==========================================

async def test_selector():
    ctx = create_mock_context()
    
    config = SelectorConfig(
        conditions=[
            ConditionBranch(expression="{{ age >= 18 }}", target_handle="adult"),
            ConditionBranch(expression="{{ age < 18 }}", target_handle="minor")
        ],
        default_handle="error"
    )
    
    runner = SelectorComponent()
    
    # Case 1: Adult
    res1 = await runner.invoke({"age": 20}, ctx, config_override=config)
    assert res1["_active_handle"] == "adult", f"Expected adult, got {res1}"
    
    # Case 2: Minor
    res2 = await runner.invoke({"age": 10}, ctx, config_override=config)
    assert res2["_active_handle"] == "minor", f"Expected minor, got {res2}"

# ==========================================
# 4. Plugin (Local Tool) 测试
# ==========================================

# 本地工具函数
def string_reverse(text: str):
    return {"reversed": text[::-1]}

async def test_plugin():
    ctx = create_mock_context()
    
    # 1. 注册工具
    tool_id = "str_rev_tool"
    ToolDefinitionRegistry.register(ToolDefinition(
        id=tool_id,
        name="Reverse String",
        source_type="builtin", # 确保使用 ToolSourceType.BUILTIN 的字符串值或枚举
        func=string_reverse
    ))
    
    # 2. 配置 Plugin
    config = PluginConfig(
        tool_id=tool_id,
        apiParam=[
            ApiParam(name="text", value="{{ target_str }}")
        ]
    )
    
    runner = PluginComponent()
    inputs = {"target_str": "hello"}
    
    # 3. 执行
    res = await runner.invoke(inputs, ctx, config_override=config)
    
    # 4. 断言
    assert res["reversed"] == "olleh"

# ==========================================
# 5. Loop 测试
# ==========================================

async def test_loop():
    ctx = create_mock_context()
    mock_executor = ctx.executor
    
    # 模拟子工作流的行为：输入 x，返回 x*2
    async def mock_sub_workflow_run(inputs, parent_ctx=None):
        # 确保 LoopComponent 正确传递了 loop_item
        val = inputs.get("loop_item")
        return {"result": val * 2}
    
    # 将 mock 挂载到 executor 上
    mock_executor.run_to_completion.side_effect = mock_sub_workflow_run
    
    # 配置 Loop (array 模式)
    dummy_workflow = WorkflowDefinition(id="dummy", nodes=[])
    config = LoopConfig(
        loop_type="array",
        sub_workflow=dummy_workflow
    )
    
    runner = LoopComponent()
    # 输入必须包含一个列表
    inputs = {"numbers": [1, 2, 3]}
    
    # 执行
    # 注意：LoopComponent 通常会自动查找 inputs 中的 list
    res = await runner.invoke(inputs, ctx, config_override=config)
    
    # 断言
    results = res["results"]
    assert len(results) == 3
    assert results[0]["result"] == 2
    assert results[1]["result"] == 4
    assert results[2]["result"] == 6
    
    # 验证 executor 被调用了 3 次
    assert mock_executor.run_to_completion.call_count == 3

# ==========================================
# 主入口
# ==========================================

async def main():
    print("🚀 Starting Standalone Component Tests...\n")
    
    await run_test("CodeRunner", test_code_runner())
    await run_test("HttpRequester", test_http_requester())
    await run_test("Selector (Switch)", test_selector())
    await run_test("Plugin (Builtin)", test_plugin())
    await run_test("Loop Component", test_loop())
    
    print("\n✨ All tests finished.")

if __name__ == "__main__":
    asyncio.run(main())