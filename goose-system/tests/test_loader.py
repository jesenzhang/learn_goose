"""
Tests for the skill loader.
"""
import tempfile
from pathlib import Path

import pytest

from goose_skill.loader import (
    SkillLoader,
    SkillMetadata,
    SkillParseError,
)


class TestSkillMetadata:
    """Tests for SkillMetadata."""

    def test_from_dict_basic(self):
        """Test creating metadata from a basic dictionary."""
        data = {"name": "test-skill", "description": "A test skill"}
        metadata = SkillMetadata.from_dict(data)

        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill"
        assert metadata.author is None
        assert metadata.version is None
        assert metadata.tags == []

    def test_from_dict_full(self):
        """Test creating metadata with all fields."""
        data = {
            "name": "full-skill",
            "description": "A full skill",
            "author": "Test Author",
            "version": "1.0.0",
            "tags": ["test", "example"],
        }
        metadata = SkillMetadata.from_dict(data)

        assert metadata.name == "full-skill"
        assert metadata.description == "A full skill"
        assert metadata.author == "Test Author"
        assert metadata.version == "1.0.0"
        assert metadata.tags == ["test", "example"]


class TestParseFrontmatter:
    """Tests for frontmatter parsing."""

    def test_valid_frontmatter(self):
        """Test parsing valid frontmatter."""
        content = """---
name: test-skill
description: A test skill
---

# Test Skill Content

This is the body of the skill.
"""
        metadata, body = SkillLoader.parse_frontmatter(content)

        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill"
        assert "# Test Skill Content" in body
        assert "This is the body" in body

    def test_frontmatter_with_extra_fields(self):
        """Test parsing frontmatter with extra fields."""
        content = """---
name: test-skill
description: A test skill
author: Test Author
version: 1.0.0
tags:
  - test
  - example
extra_field: some value
---

# Test Skill

Body content.
"""
        metadata, body = SkillLoader.parse_frontmatter(content)

        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill"
        assert metadata.author == "Test Author"
        assert metadata.version == "1.0.0"
        assert metadata.tags == ["test", "example"]

    def test_missing_frontmatter(self):
        """Test that missing frontmatter raises an error."""
        content = "# No frontmatter here"

        with pytest.raises(SkillParseError) as exc_info:
            SkillLoader.parse_frontmatter(content)

        assert "Invalid frontmatter format" in str(exc_info.value)

    def test_unclosed_frontmatter(self):
        """Test that unclosed frontmatter raises an error."""
        content = """---
name: test
description: test
"""

        with pytest.raises(SkillParseError) as exc_info:
            SkillLoader.parse_frontmatter(content)

        assert "Invalid frontmatter format" in str(exc_info.value)

    def test_missing_name_field(self):
        """Test that missing name field raises an error."""
        content = """---
description: A skill without name
---

Body content.
"""

        with pytest.raises(SkillParseError) as exc_info:
            SkillLoader.parse_frontmatter(content)

        assert "must contain 'name' field" in str(exc_info.value)


class TestParseSkillFile:
    """Tests for parsing skill files."""

    def test_parse_skill_file(self, tmp_path):
        """Test parsing a skill file."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
description: A test skill
---

# Test Skill Content
""")

        helper_file = skill_dir / "helper.py"
        helper_file.write_text("print('hello')")

        templates_dir = skill_dir / "templates"
        templates_dir.mkdir()

        template_file = templates_dir / "template.txt"
        template_file.write_text("template")

        skill = SkillLoader.parse_skill_file(skill_file)

        assert skill.metadata.name == "test-skill"
        assert skill.metadata.description == "A test skill"
        assert "# Test Skill Content" in skill.body
        assert len(skill.supporting_files) == 2

    def test_nonexistent_file(self, tmp_path):
        """Test that nonexistent file raises an error."""
        skill_file = tmp_path / "nonexistent" / "SKILL.md"

        with pytest.raises(SkillParseError) as exc_info:
            SkillLoader.parse_skill_file(skill_file)

        assert "not found" in str(exc_info.value)


class TestDiscoverSkills:
    """Tests for skill discovery."""

    def test_discover_skills(self, tmp_path):
        """Test discovering skills from a directory."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill1_dir = skills_dir / "test-skill-one-a1b2c3"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text("""---
name: test-skill-one-a1b2c3
description: First test skill
---

Body 1
""")

        skill2_dir = skills_dir / "test-skill-two-d4e5f6"
        skill2_dir.mkdir()
        (skill2_dir / "SKILL.md").write_text("""---
name: test-skill-two-d4e5f6
description: Second test skill
---

Body 2
""")

        loader = SkillLoader()
        skills = loader.discover_skills_in_directories([skills_dir])

        assert len(skills) == 2

    def test_discover_skills_from_multiple_directories(self, tmp_path):
        """Test discovering skills from multiple directories."""
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        skill1_dir = dir1 / "skill-from-dir1"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text("""---
name: skill-from-dir1
description: Skill from directory 1
---

Content from dir1
""")

        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        skill2_dir = dir2 / "skill-from-dir2"
        skill2_dir.mkdir()
        (skill2_dir / "SKILL.md").write_text("""---
name: skill-from-dir2
description: Skill from directory 2
---

Content from dir2
""")

        loader = SkillLoader()
        skills = loader.discover_skills_in_directories([dir1, dir2])

        assert len(skills) == 2
        assert "skill-from-dir1" in skills
        assert "skill-from-dir2" in skills

    def test_empty_directory(self, tmp_path):
        """Test discovering skills from an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        loader = SkillLoader()
        skills = loader.discover_skills_in_directories([empty_dir])

        assert len(skills) == 0


class TestGenerateInstructions:
    """Tests for instruction generation."""

    def test_empty_instructions(self, tmp_path):
        """Test generating instructions when no skills exist."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        loader = SkillLoader()
        skills = loader.discover_skills_in_directories([empty_dir])
        loader._skills_cache = skills

        instructions = loader.generate_instructions()

        assert instructions == ""

    def test_instructions_with_skills(self, tmp_path):
        """Test generating instructions with skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill1_dir = skills_dir / "alpha-skill"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text("""---
name: alpha-skill
description: First skill alphabetically
---

Content
""")

        skill2_dir = skills_dir / "beta-skill"
        skill2_dir.mkdir()
        (skill2_dir / "SKILL.md").write_text("""---
name: beta-skill
description: Second skill alphabetically
---

Content
""")

        loader = SkillLoader()
        skills = loader.discover_skills_in_directories([skills_dir])
        loader._skills_cache = skills

        instructions = loader.generate_instructions()

        assert "You have these skills at your disposal" in instructions
        assert "alpha-skill: First skill alphabetically" in instructions
        assert "beta-skill: Second skill alphabetically" in instructions


class TestSkillDirectories:
    """Tests for default skill directories."""

    def test_get_default_skill_directories(self):
        """Test getting default skill directories."""
        directories = SkillLoader.get_default_skill_directories()

        assert len(directories) > 0
        for dir_path in directories:
            assert isinstance(dir_path, Path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
