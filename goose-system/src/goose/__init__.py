"""
Goose-System: Python Implementation of AI Agent Framework

A modular, extensible AI Agent framework inspired by Goose-Rs,
supporting skills, tools, providers, extensions, and persistence.
"""

__version__ = "0.1.0"
__author__ = "Goose Team"

from .agent import Agent, AgentConfig
from .skills import Skill, SkillLoader, SkillRegistry
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
    "Skill",
    "SkillLoader",
    "SkillRegistry",
    "Tool",
    "ToolExecutor",
    "ToolInspector",
    "Provider",
    "create_provider",
    "ModelConfig",
    "Conversation",
    "Message",
    "PersistenceManager",
    "BaseRepository",
    "with_table",
    "TableSpec",
    "init_persistence",
    "get_persistence",
    "shutdown_persistence",
    "ExtensionManager",
    "Extension",
    "ExtensionConfig",
    "RetryManager",
    "RetryConfig",
    "PermissionManager",
    "PermissionLevel",
    "SubagentHandler",
    "SubagentConfig",
    "PromptManager",
    "PromptTemplate",
]
