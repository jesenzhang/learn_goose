"""
Unit tests for Pho Agent Core components.

Tests for:
- Core abstractions (Context, AgentResponse, AgentEvent)
- Agent engines (all 5 styles)
- Configuration
"""

import pytest
import asyncio
from pho.agent import (
    ExecutionMode,
    AgentStyle,
    AgentStatus,
    AgentEventType,
    Context,
    AgentResponse,
    AgentEvent,
    AgentConfig,
    BaseAgent,
    BaseAgentEngine,
)
from pho.conversation import Message, Role
from pho.providers import ProviderFactory, ModelConfig


# ============================================================================
# Test Core Abstractions
# ============================================================================

class TestContext:
    """Test Context data model."""

    def test_context_creation(self):
        """Test creating a context."""
        ctx = Context(
            session_id="test-session",
            user_id="test-user",
            variables={"key": "value"},
        )
        assert ctx.session_id == "test-session"
        assert ctx.user_id == "test-user"
        assert ctx.variables == {"key": "value"}

    def test_context_with_metadata(self):
        """Test context with metadata."""
        ctx = Context(
            session_id="test-session",
            user_id="test-user",
            metadata={"key": "value"},
        )
        assert ctx.metadata == {"key": "value"}


class TestAgentResponse:
    """Test AgentResponse data model."""

    def test_response_creation(self):
        """Test creating an agent response."""
        response = AgentResponse(
            text="Hello, world!",
            status=AgentStatus.COMPLETED,
            events=[{"type": "complete", "data": {}}],
        )
        assert response.text == "Hello, world!"
        assert response.status == AgentStatus.COMPLETED
        assert len(response.events) == 1

    def test_response_with_tool_calls(self):
        """Test response with tool calls."""
        response = AgentResponse(
            text="Result from tool",
            status=AgentStatus.COMPLETED,
            tool_calls=[{"name": "calculator", "result": 42}],
        )
        assert response.tool_calls[0]["result"] == 42


class TestAgentEvent:
    """Test AgentEvent data model."""

    def test_event_creation(self):
        """Test creating an agent event."""
        event = AgentEvent(
            type=AgentEventType.TOOL_START,
            data={"tool": "calculator", "args": {"a": 1, "b": 2}},
        )
        assert event.type == AgentEventType.TOOL_START
        assert event.data["tool"] == "calculator"


class TestAgentConfig:
    """Test AgentConfig data model."""

    def test_config_creation(self):
        """Test creating agent config."""
        config = AgentConfig(
            mode=ExecutionMode.REACT,
            style=AgentStyle.MINIMAL,
            system_prompt="You are a helpful assistant.",
            max_iterations=10,
        )
        assert config.mode == ExecutionMode.REACT
        assert config.style == AgentStyle.MINIMAL
        assert config.max_iterations == 10


# ============================================================================
# Test Agent Engines
# ============================================================================

class TestBaseAgentEngine:
    """Test BaseAgentEngine functionality."""

    @pytest.fixture
    def llm(self):
        """Create a mock LLM for testing."""
        return ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="test-key",
        ))

    @pytest.fixture
    def engine(self, llm):
        """Create a BaseAgentEngine for testing."""
        return BaseAgentEngine(llm=llm)

    def test_engine_creation(self, engine):
        """Test engine creation."""
        assert engine is not None
        assert engine.get_mode() == ExecutionMode.REACT
        assert engine.get_style() == AgentStyle.MINIMAL

    def test_create_conversation(self, engine):
        """Test conversation creation."""
        conversation = engine.create_conversation("Hello, Pho!", Context(
            session_id="test",
            user_id="test",
        ))
        assert conversation is not None
        messages = conversation.agent_visible_messages()
        assert len(messages) > 0

    @pytest.mark.asyncio
    async def test_engine_execute_without_api_call(self, engine):
        """Test engine execute structure (without actual API call)."""
        # This test verifies the structure without making real API calls
        context = Context(
            session_id="test-session",
            user_id="test-user",
        )
        conversation = engine.create_conversation("Test input", context)
        assert conversation is not None


# ============================================================================
# Test BaseAgent
# ============================================================================

class TestBaseAgent:
    """Test BaseAgent functionality."""

    @pytest.fixture
    def llm(self):
        """Create a mock LLM for testing."""
        return ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="test-key",
        ))

    @pytest.fixture
    def agent(self, llm):
        """Create a BaseAgent for testing."""
        return BaseAgent(
            llm=llm,
            system_prompt="You are a test assistant.",
        )

    def test_agent_creation(self, agent):
        """Test agent creation."""
        assert agent is not None
        assert agent.llm is not None
        assert agent.config is not None

    def test_agent_with_tools(self, llm):
        """Test agent with tools."""
        tools = {
            "add": lambda a, b: a + b,
            "multiply": lambda a, b: a * b,
        }
        agent = BaseAgent(llm=llm, tools=tools)
        assert agent.tools == tools

    def test_event_handler_registration(self, agent):
        """Test event handler registration."""
        # Event handlers are stored on the engine
        initial_count = len(agent.engine._event_handlers)

        @agent.on_event("start")
        async def on_start(event):
            pass

        assert len(agent.engine._event_handlers) == initial_count + 1


# ============================================================================
# Test Enums
# ============================================================================

class TestEnums:
    """Test enum values."""

    def test_execution_modes(self):
        """Test ExecutionMode enum."""
        modes = list(ExecutionMode)
        assert ExecutionMode.REACT in modes
        assert ExecutionMode.STREAMING in modes
        assert ExecutionMode.THREE_PHASE in modes
        assert ExecutionMode.WORKFLOW in modes
        assert len(modes) == 4

    def test_agent_styles(self):
        """Test AgentStyle enum."""
        styles = list(AgentStyle)
        assert AgentStyle.MINIMAL in styles
        assert AgentStyle.REACTIVE in styles
        assert AgentStyle.REASONING in styles
        assert AgentStyle.SKILL_BASED in styles
        assert AgentStyle.ORCHESTRATED in styles
        assert len(styles) == 5

    def test_agent_status(self):
        """Test AgentStatus enum."""
        statuses = list(AgentStatus)
        assert AgentStatus.IDLE in statuses
        assert AgentStatus.THINKING in statuses
        assert AgentStatus.TOOLING in statuses
        assert AgentStatus.STREAMING in statuses
        assert AgentStatus.COMPLETED in statuses
        assert AgentStatus.ERROR in statuses

    def test_agent_event_types(self):
        """Test AgentEventType enum."""
        types = list(AgentEventType)
        assert AgentEventType.START in types
        assert AgentEventType.COMPLETE in types
        assert AgentEventType.ERROR in types
        assert AgentEventType.TEXT in types
        assert AgentEventType.TOOL_START in types
        assert AgentEventType.TOOL_END in types


# ============================================================================
# Performance Tests
# ============================================================================

class TestAgentPerformance:
    """Performance tests for agent components."""

    def test_context_creation_performance(self, benchmark):
        """Benchmark context creation."""
        def create_context():
            return Context(
                session_id="test-session",
                user_id="test-user",
                variables={"key": "value"},
            )
        result = benchmark(create_context)
        assert result is not None

    def test_response_creation_performance(self, benchmark):
        """Benchmark response creation."""
        def create_response():
            return AgentResponse(
                text="Test response",
                status=AgentStatus.COMPLETED,
            )
        result = benchmark(create_response)
        assert result is not None

    def test_event_creation_performance(self, benchmark):
        """Benchmark event creation."""
        def create_event():
            return AgentEvent(
                type=AgentEventType.TEXT,
                data={"text": "test"},
            )
        result = benchmark(create_event)
        assert result is not None
