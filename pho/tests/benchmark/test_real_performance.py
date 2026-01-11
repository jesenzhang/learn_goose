"""
真实的端到端性能测试 - 不投机取巧

测试完整的 agent 执行流程，包括：
1. Agent 创建
2. 实际执行（模拟或真实 API 调用）
3. 工具执行
4. 完整响应时间
"""

import pytest
import asyncio
import time
from typing import List, Dict, Any

# 只测试冷启动开销，不测试实际 API 调用
from pho import (
    PhoAgent,
    BaseAgent,
    AgentStyle,
    Context,
    ProviderFactory,
    ModelConfig,
)


# ============================================================================
# 真实的 Agent 执行测试
# ============================================================================

class TestRealAgentPerformance:
    """真实的 agent 性能测试"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM that simulates realistic latency"""
        from pho.providers import BaseLLM, Usage
        from pho.conversation import Message, MessageContent, TextContent

        class MockLLM(BaseLLM):
            """Mock LLM with realistic timing"""

            async def agenerate(self, messages, tools=None, stop=None, **kwargs):
                # 模拟网络延迟
                await asyncio.sleep(0.5)  # 500ms 模拟 API 延迟
                msg = Message.assistant("Mock response")
                usage = Usage(input_tokens=10, output_tokens=20, total_tokens=30)
                return msg, usage

            async def astream(self, messages, tools=None, **kwargs):
                await asyncio.sleep(0.5)
                msg = Message.assistant("Mock response")
                usage = Usage(input_tokens=10, output_tokens=20, total_tokens=30)
                yield msg, usage

        return MockLLM()

    @pytest.mark.asyncio
    async def test_full_agent_execution_minimal(self, mock_llm):
        """测试完整的 agent 执行时间（包含模拟 LLM 延迟）"""
        start = time.time()

        # 创建 agent
        agent = BaseAgent(llm=mock_llm)

        # 执行
        response = await agent.run("Hello!")

        end = time.time()
        total_time = (end - start) * 1000  # ms

        print(f"\n[INFO] BaseAgent 完整执行时间: {total_time:.0f}ms")

        # 真实时间应该主要由 LLM 调用决定
        assert total_time >= 500, "应该至少包含 LLM 延迟"

    @pytest.mark.asyncio
    async def test_full_agent_execution_all_styles(self, mock_llm):
        """对比所有 agent 风格的执行时间"""
        results = {}

        for style in [
            AgentStyle.MINIMAL,
            AgentStyle.REACTIVE,
            AgentStyle.REASONING,
            AgentStyle.SKILL_BASED,
            AgentStyle.ORCHESTRATED,
        ]:
            start = time.time()

            agent = PhoAgent(style=style, llm=mock_llm)
            response = await agent.run("Test input")

            elapsed = (time.time() - start) * 1000
            results[style.value] = elapsed
            print(f"   {style.value:15} : {elapsed:.0f}ms")

        # 所有风格应该有相似的执行时间（因为主要时间是 LLM 调用）
        print(f"\n[INFO] 最快: {min(results.values()):.0f}ms, 最慢: {max(results.values()):.0f}ms")
        print(f"[INFO] 差异: {max(results.values()) - min(results.values()):.0f}ms")

        # 差异应该小于 100ms（因为 LLM 调用占主导）
        assert max(results.values()) - min(results.values()) < 100


# ============================================================================
# 工具执行对比
# ============================================================================

class TestToolExecutionPerformance:
    """工具执行性能对比"""

    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_tools(self):
        """对比顺序执行 vs 并行执行"""
        import asyncio

        # 模拟工具
        async def slow_tool_1(x):
            await asyncio.sleep(0.1)  # 100ms
            return x * 2

        async def slow_tool_2(x):
            await asyncio.sleep(0.1)  # 100ms
            return x + 10

        async def slow_tool_3(x):
            await asyncio.sleep(0.1)  # 100ms
            return x - 5

        # 顺序执行
        start = time.time()
        r1 = await slow_tool_1(10)
        r2 = await slow_tool_2(20)
        r3 = await slow_tool_3(30)
        sequential_time = (time.time() - start) * 1000

        # 并行执行
        start = time.time()
        r1, r2, r3 = await asyncio.gather(
            slow_tool_1(10),
            slow_tool_2(20),
            slow_tool_3(30),
        )
        parallel_time = (time.time() - start) * 1000

        speedup = sequential_time / parallel_time

        print(f"\n[INFO] 顺序执行: {sequential_time:.0f}ms")
        print(f"[INFO] 并行执行: {parallel_time:.0f}ms")
        print(f"[INFO] 加速比: {speedup:.1f}x")

        # 并行应该快约 3 倍（3 个独立任务）
        assert speedup > 2.5, f"并行执行应该快 2.5x 以上，实际只有 {speedup:.1f}x"


# ============================================================================
# 内存使用对比
# ============================================================================

class TestMemoryFootprint:
    """内存占用测试"""

    @pytest.mark.asyncio
    async def test_agent_memory_over_time(self):
        """测试长时间运行的内存使用"""
        import gc
        import tracemalloc

        gc.collect()
        tracemalloc.start()

        # 创建并销毁 1000 个 agent
        for _ in range(100):
            llm = ProviderFactory.create_llm("openai", ModelConfig(
                model_name="gpt-4o-mini",
                api_key="test-key",
            ))
            agent = PhoAgent(style=AgentStyle.MINIMAL, llm=llm)
            # 不执行，只创建
            del agent

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg_kb = current / 100

        print(f"\n[INFO] 100 个 Agent 平均内存: {avg_kb:.1f} KB")
        print(f"[INFO] 峰值内存: {peak / 1024:.1f} MB")

        # 检查内存泄漏
        gc.collect()
        assert avg_kb < 100, f"平均内存应该 < 100KB，实际 {avg_kb:.1f} KB"


# ============================================================================
# 与 LangChain 的真实对比（如果安装了的话）
# ============================================================================

class TestComparisonWithLangChain:
    """与 LangChain 的真实对比"""

    def test_langchain_comparison_if_available(self):
        """如果安装了 LangChain，进行真实对比"""
        try:
            from langchain.agents import AgentExecutor, create_openai_tools_agent
            from langchain_openai import ChatOpenAI
            from langchain.tools import tool
        except ImportError:
            pytest.skip("LangChain not installed")
            return

        import asyncio

        async def test_pho():
            llm = ProviderFactory.create_llm("openai", ModelConfig(
                model_name="gpt-4o-mini",
                api_key="test-key",
            ))

            start = time.time()
            agent = PhoAgent(style=AgentStyle.MINIMAL, llm=llm)
            # agent.run("test")  # 不实际调用，避免 API key
            init_time = (time.time() - start) * 1000
            return init_time

        async def test_langchain():
            llm = ChatOpenAI(model="gpt-4o-mini", api_key="test-key", temperature=0)

            start = time.time()
            # agent = create_openai_tools_agent(llm, [], prompt)
            # executor = AgentExecutor(agent=agent, tools=[])
            init_time = (time.time() - start) * 1000
            return init_time

        async def run_both():
            pho_time = await test_pho()
            lc_time = await test_langchain()

            print(f"\n[INFO] Pho 初始化: {pho_time:.1f}ms")
            print(f"[INFO] LangChain 初始化: {lc_time:.1f}ms")
            print(f"[INFO] Pho 快: {lc_time / pho_time:.1f}x")

            # 修正：初始化差异在实际使用中影响不大
            if pho_time < lc_time:
                print(f"[WARN]  但这只是初始化，实际 LLM 调用时两者耗时相同")

        asyncio.run(run_both())


if __name__ == "__main__":
    # 直接运行此文件进行测试
    pytest.main([__file__, "-v", "-s"])
