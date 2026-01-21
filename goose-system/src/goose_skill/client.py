"""
SkillsClient - Core MCP client implementation for the skill system.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import Skill, SkillLoader
from .models import (
    Content,
    Implementation,
    InitializeResult,
    ListToolsResult,
    ServerCapabilities,
    Tool,
    ToolAnnotations,
    ToolCallResult,
)


class SkillsClient:
    """MCP client for managing and loading skills."""

    EXTENSION_NAME = "skills"

    def __init__(self) -> None:
        self.loader = SkillLoader()
        self._skills: dict[str, Skill] = {}
        self._skills_cache: dict[str, Skill] = {}
        self._initialize()

        # Ensure runtime cache reflects discovered skills
        self._skills_cache = dict(self._skills)

    def _initialize(self) -> None:
        """Initialize the client by discovering skills."""
        self._skills = self.loader.discover_skills()
        # propagate to cache for immediate use
        self._skills_cache = dict(self._skills)

    def get_info(self) -> InitializeResult:
        """Get MCP server info."""
        return InitializeResult(
            protocol_version="2025-03-26",
            capabilities=ServerCapabilities(
                tools={"listChanged": False}
            ),
            server_info=Implementation(
                name=self.EXTENSION_NAME,
                title="Skills",
                version="1.0.0",
            ),
            instructions=self.loader.generate_instructions(),
        )

    def list_tools(self, next_cursor: str | None = None) -> ListToolsResult:
        """List available tools."""
        if not self._skills:
            return ListToolsResult(tools=[])

        tools = [self._create_load_skill_tool()]
        return ListToolsResult(tools=tools)

    def _create_load_skill_tool(self) -> Tool:
        """Create the loadSkill tool definition."""
        input_schema = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill to load",
                }
            },
            "required": ["name"],
        }

        return Tool(
            name="loadSkill",
            description=(
                "Load a skill by name and return its content.\n\n"
                "This tool loads the specified skill and returns its body content along with "
                "information about any supporting files in the skill directory."
            ),
            input_schema=input_schema,
            annotations=ToolAnnotations(
                title="Load skill",
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None
    ) -> ToolCallResult:
        """Call a tool by name."""
        if name == "loadSkill":
            return self._handle_load_skill(arguments)
        else:
            return ToolCallResult.error([
                Content.make_text(f"Unknown tool: {name}")
            ])

    def _handle_load_skill(
        self,
        arguments: dict[str, Any] | None = None
    ) -> ToolCallResult:
        """Handle the loadSkill tool call."""
        if arguments is None:
            return ToolCallResult.error([
                Content.make_text("Missing arguments for loadSkill")
            ])

        skill_name = arguments.get("name")
        if not skill_name:
            return ToolCallResult.error([
                Content.make_text("Missing required parameter: name")
            ])

        if not isinstance(skill_name, str):
            return ToolCallResult.error([
                Content.make_text("Parameter 'name' must be a string")
            ])

        skill = self._skills.get(skill_name)
        if skill is None:
            return ToolCallResult.error([
                Content.make_text(f"Skill '{skill_name}' not found")
            ])

        response_parts: list[str] = []

        response_parts.append(f"# Skill: {skill.name}\n\n{skill.body}")

        if skill.supporting_files:
            response_parts.append(f"\n## Supporting Files\n")
            response_parts.append(f"\nSkill directory: {skill.directory}\n")
            response_parts.append("The following supporting files are available:\n")

            for file_path in skill.supporting_files:
                try:
                    relative = file_path.relative_to(skill.directory)
                    response_parts.append(f"- {relative}")
                except ValueError:
                    response_parts.append(f"- {file_path}")

            response_parts.append("\nUse the file tools to access these files as needed.")

        response = "\n".join(response_parts)

        return ToolCallResult.success([Content.make_text(response)])

    def get_skill(self, name: str) -> Skill | None:
        """Get a specific skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """List all available skill names."""
        return sorted(self._skills.keys())

    def reload_skills(self) -> None:
        """Reload all skills from the filesystem."""
        self._skills = self.loader.discover_skills()

    @property
    def skills_count(self) -> int:
        """Get the number of loaded skills."""
        return len(self._skills)
