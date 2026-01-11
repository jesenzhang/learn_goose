"""
Pho Agent System - Multi-style agent implementation.

This package provides a unified agent framework that supports multiple execution patterns:
- BaseAgent: Minimal LLM + tools
- StreamingAgent: Event-driven with inspector chain (Goose-rs style)
- ReactAgent: Thought -> Action -> Observation loop (Claude Code style)
- ThreePhaseAgent: Intent -> LLM -> Tools (Skill Micro Agent style)
- WorkflowAgent: DAG workflow orchestration (Goose-py style)
"""

# Core abstractions
from .core import (
    # Enums
    ExecutionMode,
    AgentStyle,
    AgentStatus,
    AgentEventType,

    # Data Models
    Context,
    Thought,
    Observation,
    AgentResponse,
    AgentEvent,

    # Core Abstractions
    AgentEngine,
    ToolInspector,
    InspectorChain,

    # Configuration
    AgentConfig,
)

# Base implementations
from .base import BaseAgent, BaseAgentEngine
from .engines.base import BaseEngine
from .three_phase import ThreePhaseAgentEngine
from .workflow import WorkflowAgentEngine
from .react import ReactAgentEngine
from .streaming import StreamingAgentEngine

# Facade
from .facade import PhoAgent, create_agent

# Caching
from .cache import AgentResponseCache, CachedAgentMixin, CacheEntry

# Errors
from .errors import (
    ErrorCode,
    PhoException,
    ConfigException,
    ConfigValidationException,
    MissingConfigException,
    AgentException,
    AgentInitException,
    AgentExecutionException,
    ToolException,
    ToolNotFoundException,
    ToolExecutionException,
    ToolBlockedException,
    LLMException,
    LLMConnectionException,
    LLMRateLimitException,
    LLMTimeoutException,
    WorkflowException,
    WorkflowValidationException,
    WorkflowNotFoundException,
    handle_exception,
)

__all__ = [
    # Core
    "ExecutionMode",
    "AgentStyle",
    "AgentStatus",
    "AgentEventType",
    "Context",
    "Thought",
    "Observation",
    "AgentResponse",
    "AgentEvent",
    "AgentEngine",
    "ToolInspector",
    "InspectorChain",
    "AgentConfig",

    # Base Agent
    "BaseAgent",
    "BaseAgentEngine",
    "ThreePhaseAgentEngine",
    "WorkflowAgentEngine",
    "ReactAgentEngine",
    "StreamingAgentEngine",

    # Facade
    "PhoAgent",
    "create_agent",

    # Caching
    "AgentResponseCache",
    "CachedAgentMixin",
    "CacheEntry",

    # Errors
    "ErrorCode",
    "PhoException",
    "ConfigException",
    "ConfigValidationException",
    "MissingConfigException",
    "AgentException",
    "AgentInitException",
    "AgentExecutionException",
    "ToolException",
    "ToolNotFoundException",
    "ToolExecutionException",
    "ToolBlockedException",
    "LLMException",
    "LLMConnectionException",
    "LLMRateLimitException",
    "LLMTimeoutException",
    "WorkflowException",
    "WorkflowValidationException",
    "WorkflowNotFoundException",
    "handle_exception",
]
