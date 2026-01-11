"""
Pho Agent Core Abstractions

This module defines the core abstractions for the multi-style Agent system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ConfigDict

# Import from existing modules
from pho.conversation import Conversation, Message
from pho.providers import BaseLLM, ProviderUsage

# =============================================================================
# Enums
# =============================================================================


class ExecutionMode(str, Enum):
    """Agent execution modes"""

    REACT = "react"
    """Claude Code style: Thought → Action → Observation loop"""

    STREAMING = "streaming"
    """Goose-rs style: Async event stream with inspector chain"""

    THREE_PHASE = "three_phase"
    """Skill Micro Agent style: Intent → LLM → Tools"""

    WORKFLOW = "workflow"
    """Goose-py style: DAG workflow execution"""


class AgentStyle(str, Enum):
    """Agent style presets"""

    MINIMAL = "minimal"
    """BaseAgent: Simple LLM + tool execution"""

    REACTIVE = "reactive"
    """StreamingAgent: Event-driven with inspector chain"""

    REASONING = "reasoning"
    """ReactAgent: Explicit reasoning loop"""

    SKILL_BASED = "skill_based"
    """ThreePhaseAgent: Intent recognition + skills"""

    ORCHESTRATED = "orchestrated"
    """WorkflowAgent: DAG workflow orchestration"""


class AgentStatus(str, Enum):
    """Agent execution status"""

    IDLE = "idle"
    THINKING = "thinking"
    TOOLING = "tooling"
    STREAMING = "streaming"
    SUSPENDED = "suspended"
    ERROR = "error"
    COMPLETED = "completed"


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class Context:
    """Execution context passed to agents"""

    session_id: Optional[str] = None
    user_id: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Service injection points
    services: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Thought:
    """A single reasoning step (ReactAgent)"""

    content: str
    should_use_tool: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None


@dataclass
class Observation:
    """Result of a tool action (ReactAgent)"""

    tool_name: str
    result: Any
    is_error: bool = False
    error_message: Optional[str] = None


class AgentResponse(BaseModel):
    """Standard agent response"""

    text: str
    thoughts: List[Thought] = []
    tool_calls: List[Dict[str, Any]] = []
    usage: Optional[Dict[str, Any]] = None
    status: AgentStatus = AgentStatus.COMPLETED

    # Streaming support
    events: List[Dict[str, Any]] = []

    # Artifacts (rich outputs)
    artifacts: List[Dict[str, Any]] = []

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        populate_by_name=True,
    )


# =============================================================================
# Core Abstractions
# =============================================================================


class AgentEngine(ABC):
    """
    Base class for all agent execution engines.

    Each engine implements a specific execution pattern (React, Streaming, etc.)
    """

    @abstractmethod
    async def execute(self, input: str, context: Context) -> AgentResponse:
        """
        Execute the agent with the given input.

        Args:
            input: User input or task description
            context: Execution context with variables and services

        Returns:
            AgentResponse with results
        """
        pass

    @abstractmethod
    async def execute_stream(
        self, input: str, context: Context
    ) -> AsyncIterator[AgentResponse]:
        """
        Execute the agent with streaming output.

        Yields partial AgentResponse objects as events occur.
        """
        pass

    @abstractmethod
    def get_mode(self) -> ExecutionMode:
        """Return the execution mode this engine implements"""
        pass

    @abstractmethod
    def get_style(self) -> AgentStyle:
        """Return the agent style this engine implements"""
        pass


class ToolInspector(ABC):
    """
    Base class for tool inspectors (Goose-rs pattern).

    Inspectors validate tool calls before execution.
    """

    @abstractmethod
    async def inspect(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Message],
        context: Context,
    ) -> List[Dict[str, Any]]:
        """
        Inspect tool calls and return modified/approved calls.

        Can raise exceptions to block tool execution.
        """
        pass


class InspectorChain:
    """
    Chain of tool inspectors (Goose-rs pattern).

    Inspectors run in sequence, each can modify or block tool calls.
    """

    def __init__(self):
        self.inspectors: List[ToolInspector] = []

    def add_inspector(self, inspector: ToolInspector) -> "InspectorChain":
        """Add an inspector to the chain"""
        self.inspectors.append(inspector)
        return self

    async def inspect(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Message],
        context: Context,
    ) -> List[Dict[str, Any]]:
        """
        Run all inspectors in sequence.

        Each inspector receives the output of the previous one.
        """
        current_calls = tool_calls

        for inspector in self.inspectors:
            current_calls = await inspector.inspect(current_calls, messages, context)

        return current_calls


# =============================================================================
# Configuration
# =============================================================================


class AgentConfig(BaseModel):
    """Base configuration for all agents"""

    # Execution settings
    mode: ExecutionMode = ExecutionMode.STREAMING
    style: AgentStyle = AgentStyle.REACTIVE

    # LLM settings
    llm_config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None

    # Tool settings
    enable_tools: bool = True
    tool_approvals: bool = False  # Require approval for sensitive tools

    # Execution limits
    max_iterations: int = Field(default=10, ge=1, le=100)
    max_tokens: Optional[int] = Field(default=None, ge=1)

    # State management
    persist_state: bool = True

    # Hot reload (for ThreePhaseAgent)
    hot_reload: bool = False
    config_path: Optional[str] = None

    # Model configuration
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )


# =============================================================================
# Events
# =============================================================================

from enum import Enum


class AgentEventType(str, Enum):
    """Standard agent event types"""

    # Lifecycle
    START = "start"
    COMPLETE = "complete"
    ERROR = "error"

    # Execution phases
    THINKING = "thinking"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"

    # Content
    TOKEN = "token"
    TEXT = "text"
    THOUGHT = "thought"

    # Special
    ARTIFACT = "artifact"  # Rich output (charts, tables)
    APPROVAL_REQ = "approval_req"  # Request user approval
    STATE_CHANGE = "state_change"


class AgentEvent(BaseModel):
    """Agent event"""

    type: AgentEventType
    data: Dict[str, Any] = {}
    timestamp: float = None

    # Optional source identification
    source: Optional[str] = None
    session_id: Optional[str] = None


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "ExecutionMode",
    "AgentStyle",
    "AgentStatus",
    "AgentEventType",
    # Data Models
    "Context",
    "Thought",
    "Observation",
    "AgentResponse",
    "AgentEvent",
    # Core Abstractions
    "AgentEngine",
    "ToolInspector",
    "InspectorChain",

    # Configuration
    "AgentConfig",
]
