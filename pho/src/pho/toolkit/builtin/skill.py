"""
Skill tool for loading custom skills.

This tool provides:
- Load custom skills from SKILL.md files
- Filter by agent permissions
- Display available skills with descriptions
- Parse markdown with frontmatter
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


class SkillInfo(BaseModel):
    """Information about a skill."""

    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")
    location: str = Field(..., description="Path to SKILL.md file")


# In-memory skill registry (in production, scan filesystem)
_SKILLS: Dict[str, SkillInfo] = {}


class SkillParams(ToolInputSchema):
    """Parameters for the Skill tool."""

    name: str = Field(
        ...,
        description="The skill identifier from available_skills (e.g., 'code-review' or 'category/helper')",
    )


class SkillTool(BaseTool):
    """
    Load custom skills from SKILL.md files.

    Features:
    - Load custom skills from SKILL.md files
    - Filter by agent permissions
    - Display available skills with descriptions
    - Parse markdown with frontmatter

    Usage:
    - name (required): Skill identifier
    """

    name = "skill"
    description = (
        "Load a skill to get detailed instructions for a specific task. "
        "Skills provide specialized knowledge and step-by-step guidance. "
        "Use this when a task matches an available skill's description."
    )
    input_schema = SkillParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._skill_dirs = self.config.get("skill_dirs", [])

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the skill loading.

        Args:
            params: Dictionary containing 'name'.

        Returns:
            ToolResult with skill content.

        Raises:
            ToolError: If skill not found or loading fails.
        """
        skill_name = params["name"]

        # Get skill
        skill = _SKILLS.get(skill_name)
        if not skill:
            available = ", ".join(_SKILLS.keys()) if _SKILLS else "none"
            raise ToolError(f"Skill '{skill_name}' not found. Available skills: {available}")

        # Read and parse skill content
        try:
            skill_path = Path(skill.location)
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter if present
            parsed_content = self._parse_markdown(content)

            dir_path = str(skill_path.parent)

            output_lines = [
                f"## Skill: {skill.name}",
                "",
                f"**Base directory**: {dir_path}",
                "",
                parsed_content.strip(),
            ]

            return ToolResult(
                content="\n".join(output_lines),
                metadata={
                    "name": skill.name,
                    "dir": dir_path,
                },
            )
        except Exception as e:
            raise ToolError(f"Failed to load skill: {e}")

    def _parse_markdown(self, content: str) -> str:
        """
        Parse markdown content, extracting frontmatter.

        Args:
            content: Raw markdown content.

        Returns:
            Markdown content with frontmatter separated.
        """
        # Check for YAML frontmatter (---)
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            return match.group(2)  # Return content after frontmatter
        return content

    def discover_skills(self, base_dirs: Optional[List[str]] = None) -> None:
        """
        Discover skills in the configured directories.

        Args:
            base_dirs: List of base directories to search for skills.
        """
        _SKILLS.clear()

        # Determine search paths
        search_paths = self._skill_dirs.copy()
        if base_dirs:
            search_paths.extend(base_dirs)

        # Add default skill locations
        default_locations = [
            Path.cwd() / ".claude" / "skills",
            Path.cwd() / "skills",
            Path.home() / ".claude" / "skills",
            Path.cwd() / ".opencode" / "skill",
            Path.cwd() / ".opencode" / "skills",
        ]
        search_paths.extend([str(d) for d in default_locations if d.exists()])

        # Scan for skills
        for skill_dir in search_paths:
            if not Path(skill_dir).exists():
                continue

            skill_path = Path(skill_dir) / "SKILL.md"
            if skill_path.exists():
                try:
                    info = self._read_skill_info(skill_path)
                    _SKILLS[info.name] = info
                except Exception:
                    pass

    def _read_skill_info(self, skill_path: Path) -> SkillInfo:
        """
        Read skill information from SKILL.md file.

        Args:
            skill_path: Path to SKILL.md file.

        Returns:
            SkillInfo object.
        """
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse frontmatter
        name = "unknown"
        description = ""

        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            frontmatter = match.group(1)
            # Extract name
            name_match = re.search(r'name:\s*["\']?([^"\']+)["\']?', frontmatter)
            if name_match:
                name = name_match.group(1)
            # Extract description
            desc_match = re.search(r'description:\s*["\']?([^"\']+)["\']?', frontmatter)
            if desc_match:
                description = desc_match.group(1)

        return SkillInfo(
            name=name,
            description=description or "Custom skill",
            location=str(skill_path),
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        # Build skill list for description
        skill_descriptions = []
        for name, skill in _SKILLS.items():
            skill_descriptions.append(f"  <name>{name}</name>")
            skill_descriptions.append(f"    <description>{skill.description}</description>")

        skill_list = "\n".join(skill_descriptions)

        description = self.description
        if _SKILLS:
            description += f"\n\n<available_skills>\n{skill_list}\n</available_skills>"
        else:
            description += "\n\nNo skills are currently available."

        parameters = {
            "name": {
                "type": "string",
                "description": "The skill identifier from available_skills (e.g., 'code-review' or 'category/helper')",
                "enum": list(_SKILLS.keys()) if _SKILLS else [],
            },
        }

        return ToolInfo(
            name=self.name,
            description=description,
            parameters=parameters,
        )
