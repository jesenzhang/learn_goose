"""
Pho - A unified AI agent framework supporting workflows and skills.

This package merges goose-py (workflow framework) and skill_micro_agent (agent service)
into a single coherent framework with multi-style agent support.
"""

__version__ = "0.1.0"

# Conversation
from pho.conversation import (
    CallToolResult,
    Conversation,
    Message,
    MessageContent,
    Role,
    TextContent,
    ToolRequest,
    ToolResponse,
)

# Providers
from pho.providers import (
    BaseEmbedding,
    BaseLLM,
    BaseReranker,
    ModelConfig,
    OpenAIProvider,
    ProviderFactory,
)

# Agent System
from pho.agent import (
    # Core
    ExecutionMode,
    AgentStyle,
    AgentStatus,
    AgentEventType,
    Context,
    AgentResponse,
    AgentEvent,
    AgentConfig,

    # Base Agent
    BaseAgent,
    PhoAgent,
    create_agent,
    ThreePhaseAgentEngine,
    WorkflowAgentEngine,
    ReactAgentEngine,
    StreamingAgentEngine,
)

# Toolkit
from pho.toolkit import (
    ToolType,
    ToolMetadata,
    ToolRegistry,
    get_global_registry,
    register_tool,
    ExecutionStatus,
    ExecutionContext,
    ExecutionResult,
    ToolExecutor,
)

# Inspectors
from pho.agent.inspectors import (
    InspectorAction,
    InspectorResult,
    ToolInspector,
    InspectorChain,
    SecurityInspector,
    PermissionInspector,
    RepetitionInspector,
    Permission,
    Role,
)

# API (optional import, may not be available in all environments)
try:
    from pho.api import create_app, app, run_server
    _api_available = True
except ImportError:
    _api_available = False

__all__ = [
    # Version
    "__version__",

    # Conversation
    "Message",
    "Conversation",
    "Role",
    "MessageContent",
    "TextContent",
    "ToolRequest",
    "ToolResponse",
    "CallToolResult",

    # Providers
    "BaseLLM",
    "BaseEmbedding",
    "BaseReranker",
    "ProviderFactory",
    "ModelConfig",
    "OpenAIProvider",

    # Agent Core
    "ExecutionMode",
    "AgentStyle",
    "AgentStatus",
    "AgentEventType",
    "Context",
    "AgentResponse",
    "AgentEvent",
    "AgentConfig",

    # Agent Implementations
    "BaseAgent",
    "PhoAgent",
    "create_agent",
    "ThreePhaseAgentEngine",
    "WorkflowAgentEngine",
    "ReactAgentEngine",
    "StreamingAgentEngine",

    # Toolkit
    "ToolType",
    "ToolMetadata",
    "ToolRegistry",
    "get_global_registry",
    "register_tool",
    "ExecutionStatus",
    "ExecutionContext",
    "ExecutionResult",
    "ToolExecutor",

    # Inspectors
    "InspectorAction",
    "InspectorResult",
    "ToolInspector",
    "InspectorChain",
    "SecurityInspector",
    "PermissionInspector",
    "RepetitionInspector",
    "Permission",
    "Role",

    # API (conditional)
    "create_app",
    "app",
    "run_server",
]

# Dynamically add API to __all__ if available
if _api_available:
    pass  # Already added to __all__
