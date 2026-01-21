"""
Skill loader for discovering and parsing skills from the filesystem.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml


@dataclass
class SkillMetadata:
    """Metadata for a skill."""
    name: str
    description: str
    author: Optional[str] = None
    version: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillMetadata":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            author=data.get("author"),
            version=data.get("version"),
            tags=data.get("tags", []),
        )


@dataclass
class Skill:
    """Represents a skill loaded from the filesystem."""
    metadata: SkillMetadata
    body: str
    directory: Path
    supporting_files: list[Path] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description


class SkillParseError(Exception):
    """Error parsing a skill file."""
    pass


class SkillLoader:
    """Discovers and loads skills from the filesystem."""

    EXTENSION_NAME = "skills"

    def __init__(self):
        self._skills_cache: dict[str, Skill] = {}

    @staticmethod
    def get_default_skill_directories() -> list[Path]:
        """Get the default directories to search for skills."""
        directories: list[Path] = []

        home_dir = os.path.expanduser("~")
        if home_dir:
            directories.append(Path(home_dir) / ".claude" / "skills")
            directories.append(Path(home_dir) / ".config" / "agents" / "skills")

        config_home = os.environ.get("XDG_CONFIG_HOME")
        if config_home:
            directories.append(Path(config_home) / "skills")
        else:
            directories.append(Path(home_dir) / ".config" / "skills" if home_dir else Path("~/.config/skills"))

        try:
            working_dir = Path.cwd()
            directories.append(working_dir / ".claude" / "skills")
            directories.append(working_dir / ".goose" / "skills")
            directories.append(working_dir / ".agents" / "skills")
            # Also consider a plain 'skills' directory under the current working directory
            # This aligns with how tests place skills under <tmp>/skills
            directories.append(working_dir / "skills")
        except Exception:
            pass

        return directories

    @staticmethod
    def parse_frontmatter(content: str) -> tuple[SkillMetadata, str]:
        """
        Parse YAML frontmatter from skill content.

        Expected format:
        ---
        name: skill-name
        description: A skill description
        ---
        Markdown body here...
        """
        parts = content.split("---")

        if len(parts) < 3:
            raise SkillParseError("Invalid frontmatter format: missing delimiters")

        yaml_content = parts[1].strip()

        try:
            metadata_dict = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise SkillParseError(f"Failed to parse YAML frontmatter: {e}")

        if not isinstance(metadata_dict, dict):
            raise SkillParseError("Frontmatter must be a YAML dictionary")

        if "name" not in metadata_dict:
            raise SkillParseError("Frontmatter must contain 'name' field")

        metadata = SkillMetadata.from_dict(metadata_dict)

        body = "---".join(parts[2:]).strip()

        return metadata, body

    @staticmethod
    def find_supporting_files(directory: Path, skill_file: Path) -> list[Path]:
        """Find all supporting files in the skill directory."""
        files: list[Path] = []

        if not directory.exists() or not directory.is_dir():
            return files

        for root, dirs, filenames in os.walk(directory):
            root_path = Path(root)

            for filename in filenames:
                file_path = root_path / filename
                if file_path != skill_file and file_path.is_file():
                    files.append(file_path)

        return files

    @classmethod
    def parse_skill_file(cls, skill_file: Path) -> Skill:
        """Parse a skill from a SKILL.md file."""
        if not skill_file.exists():
            raise SkillParseError(f"Skill file not found: {skill_file}")

        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception as e:
            raise SkillParseError(f"Failed to read skill file: {e}")

        metadata, body = cls.parse_frontmatter(content)

        directory = skill_file.parent

        supporting_files = cls.find_supporting_files(directory, skill_file)

        return Skill(
            metadata=metadata,
            body=body,
            directory=directory,
            supporting_files=supporting_files,
        )

    def discover_skills_in_directories(
        self, directories: list[Path]
    ) -> dict[str, Skill]:
        """Discover all skills in the given directories."""
        skills: dict[str, Skill] = {}

        for dir_path in directories:
            if not dir_path.exists() or not dir_path.is_dir():
                continue

            try:
                for entry in dir_path.iterdir():
                    if entry.is_dir():
                        skill_file = entry / "SKILL.md"
                        if skill_file.exists():
                            try:
                                skill = self.parse_skill_file(skill_file)
                                skills[skill.name] = skill
                            except SkillParseError as e:
                                print(f"Warning: Failed to parse skill {skill_file}: {e}")
            except Exception as e:
                print(f"Warning: Error scanning directory {dir_path}: {e}")

        return skills

    def discover_skills(self) -> dict[str, Skill]:
        """Discover all skills in default directories."""
        directories = self.get_default_skill_directories()
        existing_dirs = [d for d in directories if d.exists()]
        return self.discover_skills_in_directories(existing_dirs)

    def load_skill(self, name: str) -> Skill | None:
        """Load a specific skill by name."""
        if name not in self._skills_cache:
            skills = self.discover_skills()
            self._skills_cache = skills

        return self._skills_cache.get(name)

    def get_skill_names(self) -> list[str]:
        """Get list of all skill names."""
        skills = self.discover_skills()
        return sorted(skills.keys())

    def generate_instructions(self) -> str:
        """Generate instructions for the model about available skills."""
        skills = self._skills_cache

        if not skills:
            return ""

        lines = [
            "You have these skills at your disposal, when it is clear they can help you solve a problem or you are asked to use them:\n"
        ]

        for name, skill in sorted(skills.items()):
            lines.append(f"- {name}: {skill.description}")

        return "\n".join(lines)
