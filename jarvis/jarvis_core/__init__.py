"""Jarvis - Event-sourced, Replayable Agent Runtime

A production-grade Agent Runtime with:
- Event Sourcing
- Pure Agent Reducers
- Effect-based Execution
- Async/Concurrent support
"""

__version__ = "0.1.0"

# Core - use relative imports to avoid circular reference
from .core import *
from .store import *
from .executor import *
from .runtime import *

# Optional: from assistant (may not be available)
try:
    from .providers import *
    _has_providers = True
except Exception:
    _has_providers = False

try:
    from .conversation import *
    _has_conversation = True
except Exception:
    _has_conversation = False

try:
    from .skills import *
    _has_skills = True
except Exception:
    _has_skills = False

try:
    from .intent import *
    _has_intent = True
except Exception:
    _has_intent = False


__all__ = [
    # Core
    "Event", "EventType", "SystemEvents",
    "AgentState", "AgentStatus",
    "Effect", "EffectType",
    "Agent", "SimpleChatAgent", "ToolUsingAgent",
    "TaskHandle",

    # Store
    "EventStore", "MemoryEventStore", "SQLiteEventStore",
    "StateStore", "MemoryStateStore", "SQLiteStateStore",
    "SnapshotManager",

    # Executor
    "EffectExecutor", "ExecutionResult",
    "MockExecutor", "RealExecutor",
    "LLMExecutor", "MockLLMExecutor", "OpenAIExecutor",

    # Runtime
    "Runtime", "RuntimeSession", "create_runtime",

    # Providers (from assistant, if available)
    "BaseLLM", "BaseEmbedding",
    "ProviderFactory", "OpenAIProvider",

    # Conversation (from assistant, if available)
    "Message", "Role", "MessageContent",

    # Skills (from assistant, if available)
    "SkillLoader", "SkillBase",

    # Intent (from assistant, if available)
    "IntentRecognizer", "IntentDefinition", "IntentResult",

    # Full Assistant Agent
    "FullAssistantAgent",
]

# Mark availability
__has_providers__ = _has_providers
__has_conversation__ = _has_conversation
__has_skills__ = _has_skills
__has_intent__ = _has_intent
