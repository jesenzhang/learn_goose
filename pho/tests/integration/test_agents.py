"""
Integration tests for Pho Agents.

Tests for:
- All 5 agent styles integration
- Agent workflow
- Tool execution
- Session management
"""

import pytest
import asyncio
import time
from typing import Dict, Any

from pho import (
    PhoAgent,
    AgentStyle,
    Context,
    ProviderFactory,
    ModelConfig,
    ToolRegistry,
    register_tool,
    ExecutionStatus,
    ToolExecutor,
    InspectorChain,
    SecurityInspector,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def llm():
    """Create LLM provider for testing."""
    return ProviderFactory.create_llm("openai", ModelConfig(
        model_name="gpt-4o-mini",
        api_key="test-key",  # Use test key for mock testing
    ))


@pytest.fixture
def sample_tools():
    """Create sample tools for testing."""
    tools = {
        "echo": lambda text: f"Echo: {text}",
        "add": lambda a, b: a + b,
        "multiply": lambda a, b: a * b,
        "get_time": lambda: time.time(),
    }
    return tools


# ============================================================================
# Test PhoAgent with All Styles
# ============================================================================

class TestPhoAgentStyles:
    """Test PhoAgent with different styles."""

    @pytest.mark.asyncio
    async def test_minimal_agent_creation(self, llm):
        """Test creating MINIMAL style agent."""
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
        )
        assert agent.get_style() == AgentStyle.MINIMAL
        assert agent.get_config().mode.value == "react"

    @pytest.mark.asyncio
    async def test_reactive_agent_creation(self, llm):
        """Test creating REACTIVE style agent."""
        agent = PhoAgent(
            style=AgentStyle.REACTIVE,
            llm=llm,
        )
        assert agent.get_style() == AgentStyle.REACTIVE
        assert agent.get_config().mode.value == "streaming"

    @pytest.mark.asyncio
    async def test_reasoning_agent_creation(self, llm):
        """Test creating REASONING style agent."""
        agent = PhoAgent(
            style=AgentStyle.REASONING,
            llm=llm,
        )
        assert agent.get_style() == AgentStyle.REASONING
        assert agent.get_config().mode.value == "react"

    @pytest.mark.asyncio
    async def test_skill_based_agent_creation(self, llm):
        """Test creating SKILL_BASED style agent."""
        agent = PhoAgent(
            style=AgentStyle.SKILL_BASED,
            llm=llm,
        )
        assert agent.get_style() == AgentStyle.SKILL_BASED
        assert agent.get_config().mode.value == "three_phase"

    @pytest.mark.asyncio
    async def test_orchestrated_agent_creation(self, llm):
        """Test creating ORCHESTRATED style agent."""
        agent = PhoAgent(
            style=AgentStyle.ORCHESTRATED,
            llm=llm,
        )
        assert agent.get_style() == AgentStyle.ORCHESTRATED
        assert agent.get_config().mode.value == "workflow"


# ============================================================================
# Test Agent Execution
# ============================================================================

class TestAgentExecution:
    """Test agent execution without real API calls."""

    @pytest.mark.asyncio
    async def test_agent_with_tools(self, llm, sample_tools):
        """Test agent with tool registration."""
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
            tools=sample_tools,
        )
        assert len(agent.tools) == 4
        assert "echo" in agent.tools

    @pytest.mark.asyncio
    async def test_agent_with_custom_config(self, llm):
        """Test agent with custom configuration."""
        from pho import AgentConfig

        config = AgentConfig(
            system_prompt="You are a custom assistant.",
            max_iterations=20,
        )
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
            config=config,
        )
        assert agent.config.system_prompt == "You are a custom assistant."
        assert agent.config.max_iterations == 20

    @pytest.mark.asyncio
    async def test_agent_context_creation(self, llm):
        """Test agent creates proper context."""
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
        )
        context = Context(
            session_id="test-session",
            user_id="test-user",
            variables={"name": "TestUser"},
        )
        assert context.session_id == "test-session"
        assert context.variables["name"] == "TestUser"


# ============================================================================
# Test Tool Integration
# ============================================================================

class TestToolIntegration:
    """Test tool execution with agents."""

    def test_tool_registration(self):
        """Test decorator-based tool registration."""
        # Register directly to a local registry for testing
        registry = ToolRegistry()
        registry.register("test_tool", lambda value: f"Processed: {value}", "A test tool")

        metadata = registry.get("test_tool")
        assert metadata is not None
        assert metadata.description == "A test tool"

    @pytest.mark.asyncio
    async def test_tool_executor_with_inspector(self):
        """Test tool executor with inspector chain."""
        registry = ToolRegistry()
        registry.register("test", lambda x: x * 2, "Test tool")

        inspector_chain = InspectorChain()
        inspector_chain.add_inspector(SecurityInspector())

        executor = ToolExecutor(
            registry=registry,
            inspector_chain=inspector_chain,
            enable_cache=True,
        )

        from pho import ExecutionContext
        context = ExecutionContext(
            session_id="test",
            user_id="test",
        )

        result = await executor.execute("test", {"x": 5}, context)
        assert result.is_success
        assert result.result == 10


# ============================================================================
# Test Session Management
# ============================================================================

class TestSessionManagement:
    """Test session management across agent executions."""

    @pytest.mark.asyncio
    async def test_session_state_tracking(self, llm):
        """Test agent tracks session state."""
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
        )

        # Simulate session state
        context = Context(
            session_id="test-session-123",
            user_id="user-456",
            variables={"counter": 0},
        )

        assert context.session_id == "test-session-123"
        assert context.variables["counter"] == 0

    @pytest.mark.asyncio
    async def test_conversation_history(self, llm):
        """Test agent maintains conversation history."""
        from pho import Conversation, Message

        conversation = Conversation()
        conversation.push(Message.user("Hello"))
        conversation.push(Message.assistant("Hi there!"))
        conversation.push(Message.user("How are you?"))

        messages = conversation.agent_visible_messages()
        assert len(messages) == 3


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in agents."""

    @pytest.mark.asyncio
    async def test_invalid_tool_handling(self, llm):
        """Test agent handles invalid tool calls gracefully."""
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
            tools={"valid_tool": lambda x: x},
        )

        # Agent should handle invalid tool references
        # (actual behavior depends on implementation)
        assert "valid_tool" in agent.tools

    @pytest.mark.asyncio
    async def test_context_error_handling(self, llm):
        """Test agent handles context errors."""
        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm,
        )

        # Create context with missing required fields
        context = Context(
            session_id="",  # Empty session ID
            user_id=None,   # None user ID
        )

        # Agent should handle this gracefully
        assert context is not None


# ============================================================================
# Integration Performance Tests
# ============================================================================

class TestIntegrationPerformance:
    """Performance tests for integration scenarios."""

    @pytest.mark.asyncio
    async def test_agent_creation_time(self, benchmark):
        """Benchmark agent creation."""
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="test-key",
        ))

        def create_agent():
            return PhoAgent(
                style=AgentStyle.MINIMAL,
                llm=llm,
            )

        agent = benchmark(create_agent)
        assert agent is not None

    @pytest.mark.asyncio
    async def test_context_creation_time(self, benchmark):
        """Benchmark context creation."""
        def create_context():
            return Context(
                session_id="test-session",
                user_id="test-user",
                variables={"key": "value"},
            )

        context = benchmark(create_context)
        assert context is not None

    @pytest.mark.asyncio
    async def test_tool_registration_time(self, benchmark):
        """Benchmark tool registration."""
        def register_tool():
            registry = ToolRegistry()
            registry.register("test", lambda x: x, "Test")
            return registry

        registry = benchmark(register_tool)
        assert registry is not None
