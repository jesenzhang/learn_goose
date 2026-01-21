"""
Tests for the SkillsClient.
"""
from pathlib import Path

import pytest

from goose_skill.client import SkillsClient
from goose_skill.loader import SkillLoader


def create_test_skill(tmp_path, name: str, description: str, body: str = "Content"):
    """Helper to create a test skill."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_dir = skills_dir / name
    skill_dir.mkdir()

    (skill_dir / "SKILL.md").write_text(f"""---
name: {name}
description: {description}
---

{body}
""")

    (skill_dir / "helper.py").write_text("print('hello')")

    return skills_dir


class TestSkillsClient:
    """Tests for SkillsClient."""

    def test_get_info(self, tmp_path, monkeypatch):
        """Test getting server info."""
        skills_dir = create_test_skill(tmp_path, "test-skill", "A test skill")
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()

        info = client.get_info()

        assert info.protocol_version == "2025-03-26"
        assert info.server_info.name == "skills"
        assert info.server_info.title == "Skills"
        assert info.server_info.version == "1.0.0"
        assert "test-skill" in (info.instructions or "")

    def test_list_tools_with_skills(self, tmp_path, monkeypatch):
        """Test listing tools when skills exist."""
        skills_dir = create_test_skill(tmp_path, "test-skill", "A test skill")
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()
        result = client.list_tools()

        assert len(result.tools) == 1
        assert result.tools[0].name == "loadSkill"

    def test_list_tools_without_skills(self, tmp_path, monkeypatch):
        """Test listing tools when no skills exist."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.list_tools()

        assert len(result.tools) == 0

    def test_call_load_skill(self, tmp_path, monkeypatch):
        """Test calling loadSkill tool."""
        skills_dir = create_test_skill(
            tmp_path, "test-skill", "A test skill", "This is the body of the skill."
        )
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()
        result = client.call_tool("loadSkill", {"name": "test-skill"})

        assert not result.is_error
        assert len(result.content) == 1
        assert "test-skill" in result.content[0].text
        assert "This is the body of the skill" in result.content[0].text

    def test_call_load_skill_with_supporting_files(self, tmp_path, monkeypatch):
        """Test calling loadSkill with supporting files."""
        skills_dir = create_test_skill(tmp_path, "test-skill", "A test skill")
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()
        result = client.call_tool("loadSkill", {"name": "test-skill"})

        assert not result.is_error
        assert "Supporting Files" in result.content[0].text
        assert "helper.py" in result.content[0].text

    def test_call_load_skill_not_found(self, tmp_path, monkeypatch):
        """Test calling loadSkill with nonexistent skill."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.call_tool("loadSkill", {"name": "nonexistent"})

        assert result.is_error
        assert "not found" in result.content[0].text

    def test_call_load_skill_missing_args(self, tmp_path, monkeypatch):
        """Test calling loadSkill without arguments."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.call_tool("loadSkill", None)

        assert result.is_error
        assert "Missing arguments" in result.content[0].text

    def test_call_load_skill_missing_name(self, tmp_path, monkeypatch):
        """Test calling loadSkill without name parameter."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.call_tool("loadSkill", {})

        assert result.is_error
        assert "Missing required parameter: name" in result.content[0].text

    def test_call_unknown_tool(self, tmp_path, monkeypatch):
        """Test calling an unknown tool."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.call_tool("unknown_tool", {})

        assert result.is_error
        assert "Unknown tool" in result.content[0].text

    def test_get_skill(self, tmp_path, monkeypatch):
        """Test getting a specific skill."""
        skills_dir = create_test_skill(tmp_path, "test-skill", "A test skill")
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()
        skill = client.get_skill("test-skill")

        assert skill is not None
        assert skill.name == "test-skill"

    def test_get_skill_not_found(self, tmp_path, monkeypatch):
        """Test getting a nonexistent skill."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        skill = client.get_skill("nonexistent")

        assert skill is None

    def test_list_skills(self, tmp_path, monkeypatch):
        """Test listing all skill names."""
        skills_dir = create_test_skill(tmp_path, "test-skill", "A test skill")
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()
        names = client.list_skills()

        assert "test-skill" in names

    def test_skills_count(self, tmp_path, monkeypatch):
        """Test getting the skills count."""
        skills_dir = create_test_skill(tmp_path, "test-skill", "A test skill")
        monkeypatch.chdir(skills_dir.parent)

        client = SkillsClient()
        assert client.skills_count >= 1


class TestLoadSkillToolDefinition:
    """Tests for the loadSkill tool definition."""

    def test_tool_has_correct_schema(self, tmp_path, monkeypatch):
        """Test that the loadSkill tool has the correct input schema."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.list_tools()

        assert len(result.tools) == 1
        tool = result.tools[0]

        assert tool.name == "loadSkill"
        assert "name" in tool.input_schema.get("properties", {})
        assert "name" in tool.input_schema.get("required", [])

    def test_tool_has_annotations(self, tmp_path, monkeypatch):
        """Test that the loadSkill tool has annotations."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        client = SkillsClient()
        result = client.list_tools()

        assert len(result.tools) == 1
        tool = result.tools[0]

        assert tool.annotations is not None
        assert tool.annotations.title == "Load skill"
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
