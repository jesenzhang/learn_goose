"""
Performance benchmarks for Pho Framework.

Measures:
- Agent initialization time
- Context creation overhead
- Response generation latency
- Memory footprint
- Throughput

Run with: pytest tests/benchmark/test_performance.py --benchmark-only
"""

import pytest
import time
import asyncio
import gc
import tracemalloc
from typing import List, Dict, Any

from pho import (
    PhoAgent,
    BaseAgent,
    AgentStyle,
    AgentStatus,
    Context,
    AgentResponse,
    AgentEvent,
    AgentEventType,
    ProviderFactory,
    ModelConfig,
    ToolRegistry,
    Conversation,
    Message,
)


# ============================================================================
# Benchmark Fixtures
# ============================================================================

@pytest.fixture
def llm():
    """Create LLM provider for benchmarks."""
    return ProviderFactory.create_llm("openai", ModelConfig(
        model_name="gpt-4o-mini",
        api_key="benchmark-key",
    ))


@pytest.fixture
def sample_tools():
    """Sample tools for benchmarking."""
    return {
        "add": lambda a, b: a + b,
        "multiply": lambda a, b: a * b,
        "divide": lambda a, b: a / b,
        "concat": lambda a, b: f"{a}{b}",
        "get_length": lambda x: len(x),
    }


# ============================================================================
# Agent Creation Benchmarks
# ============================================================================

class TestAgentCreationPerformance:
    """Benchmark agent creation times."""

    def test_base_agent_creation(self, benchmark, llm):
        """Benchmark BaseAgent creation."""
        def create_agent():
            return BaseAgent(llm=llm)

        agent = benchmark(create_agent)
        assert agent is not None

    def test_pho_agent_minimal(self, benchmark, llm):
        """Benchmark PhoAgent with MINIMAL style."""
        def create_agent():
            return PhoAgent(style=AgentStyle.MINIMAL, llm=llm)

        agent = benchmark(create_agent)
        assert agent.get_style() == AgentStyle.MINIMAL

    def test_pho_agent_reactive(self, benchmark, llm):
        """Benchmark PhoAgent with REACTIVE style."""
        def create_agent():
            return PhoAgent(style=AgentStyle.REACTIVE, llm=llm)

        agent = benchmark(create_agent)
        assert agent.get_style() == AgentStyle.REACTIVE

    def test_pho_agent_reasoning(self, benchmark, llm):
        """Benchmark PhoAgent with REASONING style."""
        def create_agent():
            return PhoAgent(style=AgentStyle.REASONING, llm=llm)

        agent = benchmark(create_agent)
        assert agent.get_style() == AgentStyle.REASONING

    def test_pho_agent_with_tools(self, benchmark, llm, sample_tools):
        """Benchmark PhoAgent with tools."""
        def create_agent():
            return PhoAgent(
                style=AgentStyle.MINIMAL,
                llm=llm,
                tools=sample_tools,
            )

        agent = benchmark(create_agent)
        assert len(agent.tools) == 5

    def test_pho_agent_all_styles(self, benchmark, llm):
        """Benchmark creating all agent styles."""
        styles = [
            AgentStyle.MINIMAL,
            AgentStyle.REACTIVE,
            AgentStyle.REASONING,
            AgentStyle.SKILL_BASED,
            AgentStyle.ORCHESTRATED,
        ]

        def create_all_agents():
            return [PhoAgent(style=s, llm=llm) for s in styles]

        agents = benchmark(create_all_agents)
        assert len(agents) == 5


# ============================================================================
# Context & Data Structure Benchmarks
# ============================================================================

class TestDataStructurePerformance:
    """Benchmark data structure operations."""

    def test_context_creation(self, benchmark):
        """Benchmark Context creation."""
        def create_context():
            return Context(
                session_id=f"session-{time.time()}",
                user_id=f"user-{time.time()}",
                variables={
                    "key1": "value1",
                    "key2": "value2",
                    "key3": 123,
                    "key4": True,
                },
            )

        context = benchmark(create_context)
        assert context is not None

    def test_response_creation(self, benchmark):
        """Benchmark AgentResponse creation."""
        def create_response():
            return AgentResponse(
                text="This is a test response with some content.",
                status=AgentStatus.COMPLETED,
                events=[
                    {"type": AgentEventType.TEXT, "data": {"text": "chunk"}},
                    {"type": AgentEventType.COMPLETE, "data": {}},
                ],
            )

        response = benchmark(create_response)
        assert response.text is not None

    def test_conversation_creation(self, benchmark):
        """Benchmark Conversation with messages."""
        def create_conversation():
            conv = Conversation()
            conv.push(Message.user("Hello"))
            conv.push(Message.assistant("Hi there!"))
            conv.push(Message.user("How are you?"))
            return conv

        conv = benchmark(create_conversation)
        assert len(conv.messages) == 3

    def test_message_creation(self, benchmark):
        """Benchmark Message creation."""
        def create_message():
            return Message.user("This is a test message content.")

        message = benchmark(create_message)
        assert message.role == "user"


# ============================================================================
# Tool Operation Benchmarks
# ============================================================================

class TestToolPerformance:
    """Benchmark tool operations."""

    def test_tool_registration(self, benchmark):
        """Benchmark tool registration."""
        def register_tools():
            registry = ToolRegistry()
            for i in range(10):
                registry.register(
                    f"tool_{i}",
                    lambda x: x,
                    f"Tool {i}",
                )
            return registry

        registry = benchmark(register_tools)
        assert len(registry) == 10

    def test_tool_lookup(self, benchmark):
        """Benchmark tool lookup."""
        registry = ToolRegistry()
        for i in range(100):
            registry.register(f"tool_{i}", lambda x: x, f"Tool {i}")

        def lookup_tool():
            return registry.get("tool_50")

        metadata = benchmark(lookup_tool)
        assert metadata is not None

    def test_tool_execution_sync(self, benchmark):
        """Benchmark synchronous tool execution."""
        def sync_tool():
            return sum(range(1000))

        result = benchmark(sync_tool)
        assert result == 499500

    @pytest.mark.asyncio
    async def test_tool_execution_async(self, benchmark):
        """Benchmark asynchronous tool execution."""
        async def async_tool():
            await asyncio.sleep(0.001)
            return sum(range(1000))

        result = await benchmark(async_tool)
        assert result == 499500


# ============================================================================
# Memory Benchmarks
# ============================================================================

class TestMemoryPerformance:
    """Benchmark memory usage."""

    def test_agent_memory_footprint(self):
        """Measure memory footprint of agent creation."""
        gc.collect()
        tracemalloc.start()

        # Create 100 agents
        agents = []
        for _ in range(100):
            llm = ProviderFactory.create_llm("openai", ModelConfig(
                model_name="gpt-4o-mini",
                api_key="test-key",
            ))
            agent = PhoAgent(style=AgentStyle.MINIMAL, llm=llm)
            agents.append(agent)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg_kb = current / 100
        print(f"\n📊 Memory per agent: {avg_kb:.1f} KB")
        print(f"📊 Peak memory: {peak / 1024:.1f} MB")

        # Target: < 30 MB per agent (30000 KB)
        assert avg_kb < 30000, f"Agent memory too high: {avg_kb:.1f} KB"

    def test_conversation_memory_footprint(self):
        """Measure memory footprint of conversations."""
        gc.collect()
        tracemalloc.start()

        # Create 100 conversations with 10 messages each
        conversations = []
        for _ in range(100):
            conv = Conversation()
            for i in range(10):
                conv.push(Message.user(f"Message {i}"))
                conv.push(Message.assistant(f"Response {i}"))
            conversations.append(conv)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg_kb = current / 100
        print(f"\n📊 Memory per conversation (20 msgs): {avg_kb:.1f} KB")
        print(f"📊 Peak memory: {peak / 1024:.1f} MB")

        # Target: < 50 KB per conversation with 20 messages
        assert avg_kb < 50, f"Conversation memory too high: {avg_kb:.1f} KB"


# ============================================================================
# Throughput Benchmarks
# ============================================================================

class TestThroughputPerformance:
    """Benchmark throughput metrics."""

    def test_context_creation_throughput(self, benchmark):
        """Benchmark context creation throughput (create 1000)."""
        def create_1000_contexts():
            contexts = []
            for i in range(1000):
                ctx = Context(
                    session_id=f"session-{i}",
                    user_id=f"user-{i}",
                )
                contexts.append(ctx)
            return contexts

        contexts = benchmark(create_1000_contexts)
        assert len(contexts) == 1000

    def test_message_creation_throughput(self, benchmark):
        """Benchmark message creation throughput (create 10000)."""
        def create_10000_messages():
            messages = []
            for i in range(10000):
                msg = Message.user(f"Message {i}")
                messages.append(msg)
            return messages

        messages = benchmark(create_10000_messages)
        assert len(messages) == 10000


# ============================================================================
# Latency Benchmarks
# ============================================================================

class TestLatencyPerformance:
    """Benchmark operation latencies."""

    def test_agent_init_latency(self, benchmark):
        """Measure agent initialization latency."""
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="test-key",
        ))

        def init_agent():
            return PhoAgent(style=AgentStyle.MINIMAL, llm=llm)

        # Target: < 100ms
        agent = benchmark(init_agent)
        assert agent is not None

    def test_context_creation_latency(self, benchmark):
        """Measure context creation latency."""
        def create_context():
            return Context(
                session_id="test-session",
                user_id="test-user",
                variables={"key": "value"},
            )

        # Target: < 1ms
        context = benchmark(create_context)
        assert context is not None


# ============================================================================
# Comparison Report Generator
# ============================================================================

@pytest.mark.skip(reason="Manual report generation")
def test_generate_comparison_report():
    """Generate a comparison report with similar products."""
    report = {
        "Pho Framework v0.1.0": {
            "Agent Init Time (ms)": "TBD",
            "Context Creation (µs)": "TBD",
            "Memory per Agent (KB)": "TBD",
            "Throughput (contexts/sec)": "TBD",
        },
        "LangChain": {
            "Agent Init Time (ms)": "~100",
            "Context Creation (µs)": "~50",
            "Memory per Agent (KB)": "~25000",
            "Throughput (contexts/sec)": "~1000",
        },
        "AutoGen": {
            "Agent Init Time (ms)": "~150",
            "Context Creation (µs)": "~80",
            "Memory per Agent (KB)": "~30000",
            "Throughput (contexts/sec)": "~800",
        },
        "Semantic Kernel": {
            "Agent Init Time (ms)": "~120",
            "Context Creation (µs)": "~60",
            "Memory per Agent (KB)": "~28000",
            "Throughput (contexts/sec)": "~900",
        },
    }

    print("\n" + "=" * 80)
    print("PERFORMANCE COMPARISON REPORT")
    print("=" * 80)
    print(f"{'Metric':<30} {'Pho':>15} {'LangChain':>15} {'AutoGen':>15} {'SK':>15}")
    print("-" * 80)

    for metric in report["Pho Framework v0.1.0"].keys():
        print(f"{metric:<30}", end="")
        for product in ["Pho Framework v0.1.0", "LangChain", "AutoGen", "Semantic Kernel"]:
            value = report[product][metric]
            print(f"{value:>15}", end="")
        print()

    print("=" * 80)
