"""
Goose-System: Python Implementation of AI Agent Framework

A modular, extensible AI Agent framework inspired by Goose-Rs,
supporting skills, tools, providers, extensions, and persistence.
"""

__version__ = "0.1.0"
__author__ = "Goose Team"

from .agent import Agent, AgentConfig
from .skills import (
    Skill,
    SkillLoader,
    SkillRegistry,
    SkillMetadata,
    ProgressiveDisclosureStateMachine,
    SkillState,
    ToolInterceptor,
    ToolPermission,
    ResourceLoader,
    ResourceValidator,
    SandboxIntegrator,
    ExecutionResult,
    StandardPathDiscovery,
    ConfigurablePathDiscovery,
    PathDiscoveryResult,
    SecurityLevel,
    SecurityViolation,
    ThreatType,
    SecurityCheckResult,
    SecurityReport,
    EnhancedStaticScanner,
    ArtifactSanitizer,
    SecurityManager,
    PromptInjectionDefense,
)
from .tools import Tool, ToolExecutor, ToolInspector
from .providers import Provider, create_provider, ModelConfig
from .conversation import Conversation, Message
from .persistence import (
    PersistenceManager,
    BaseRepository,
    with_table,
    TableSpec,
    init_persistence,
    get_persistence,
    shutdown_persistence,
)
from .extension import (
    ExtensionManager,
    Extension,
    ExtensionConfig,
)
from .session import (
    SessionManager,
    SessionState,
    SessionMessage,
    SharedStateManager,
    create_session_manager,
)
from .managers import (
    RetryManager,
    RetryConfig,
    PermissionManager,
    PermissionLevel,
    SubagentHandler,
    SubagentConfig,
    PromptManager,
    PromptTemplate,
)

__all__ = [
    "Agent",
    "AgentConfig",
    # Skills
    "Skill",
    "SkillLoader",
    "SkillRegistry",
    "SkillMetadata",
    "ProgressiveDisclosureStateMachine",
    "SkillState",
    "ToolInterceptor",
    "ToolPermission",
    "ResourceLoader",
    "ResourceValidator",
    "SandboxIntegrator",
    "ExecutionResult",
    "StandardPathDiscovery",
    "ConfigurablePathDiscovery",
    "PathDiscoveryResult",
    # Security (v2.0)
    "SecurityLevel",
    "SecurityViolation",
    "ThreatType",
    "SecurityCheckResult",
    "SecurityReport",
    "EnhancedStaticScanner",
    "ArtifactSanitizer",
    "SecurityManager",
    "PromptInjectionDefense",
    # Tools
    "Tool",
    "ToolExecutor",
    "ToolInspector",
    # Providers
    "Provider",
    "create_provider",
    "ModelConfig",
    # Conversation
    "Conversation",
    "Message",
    # Persistence
    "PersistenceManager",
    "BaseRepository",
    "with_table",
    "TableSpec",
    "init_persistence",
    "get_persistence",
    "shutdown_persistence",
    # Extension
    "ExtensionManager",
    "Extension",
    "ExtensionConfig",
    # Managers
    "RetryManager",
    "RetryConfig",
    "PermissionManager",
    "PermissionLevel",
    "SubagentHandler",
    "SubagentConfig",
    "PromptManager",
    "PromptTemplate",
]
