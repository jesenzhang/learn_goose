"""
Goose Skill System - Python Implementation

A skill management system inspired by Goose-RS, providing
declarative skill definitions with YAML frontmatter + Markdown.
"""

from .loader import Skill, SkillMetadata, SkillLoader
from .client import SkillsClient
from .models import Tool, ToolCallResult, ListToolsResult

__version__ = "1.0.0"
__all__ = [
    "Skill",
    "SkillMetadata",
    "SkillLoader",
    "SkillsClient",
    "Tool",
    "ToolCallResult",
    "ListToolsResult",
]
