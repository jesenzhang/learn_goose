"""
Skills Module Init

Skills 模块初始化
"""

from .base import Skill, SkillMetadata, parse_skill_metadata
from .loader import SkillLoader, SkillBackend, FilesystemBackend, MemoryBackend, SKILLS_SYSTEM_PROMPT, format_skills_for_prompt
from .registry import SkillRegistry, SkillInfo
from .impl_loader import (
    SkillImplLoader,
    load_impl_module,
    get_callable_from_module,
    create_tool_from_impl_function,
    load_skill_with_implementation,
)

__all__ = [
    "Skill",
    "SkillMetadata",
    "parse_skill_metadata",
    "SkillLoader",
    "SkillBackend",
    "FilesystemBackend",
    "MemoryBackend",
    "SKILLS_SYSTEM_PROMPT",
    "format_skills_for_prompt",
    "SkillRegistry",
    "SkillInfo",
    "SkillImplLoader",
    "load_impl_module",
    "get_callable_from_module",
    "create_tool_from_impl_function",
    "load_skill_with_implementation",
]
