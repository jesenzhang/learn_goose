"""
Skills Module - Skill system for MicroAgent.

Provides:
- Skill base classes
- Service context for dependency injection
- Skill loader for discovery and registration
"""

from .base import (
    SkillBase,
    GlobalSkill,
    ContextualSkill,
    skill_tool,
    ToolMetadata,
    SkillType
)
from .context import (
    ServiceContext,
    ServiceContextBuilder,
    ServiceLocator,
    DictServiceLocator,
    create_context
)
from .loader import SkillLoader
from .generic import GenericSkill

__all__ = [
    # Base classes
    "SkillBase",
    "GlobalSkill",
    "ContextualSkill",
    "skill_tool",
    "ToolMetadata",
    "SkillType",

    # Context
    "ServiceContext",
    "ServiceContextBuilder",
    "ServiceLocator",
    "DictServiceLocator",
    "create_context",

    # Loader
    "SkillLoader",

    # Generic
    "GenericSkill",
]
