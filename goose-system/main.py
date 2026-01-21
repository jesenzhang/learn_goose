#!/usr/bin/env python3
"""
Goose Skill System - Main Entry Point

A skill management system inspired by Goose-RS, providing
declarative skill definitions with YAML frontmatter + Markdown.
"""

from pathlib import Path

from goose_skill import SkillsClient, SkillLoader


def main():
    """Main entry point for the skill system."""
    print("Goose Skill System")
    print("=" * 50)

    loader = SkillLoader()
    skills = loader.discover_skills()

    print(f"\nDiscovered {len(skills)} skill(s):")
    for name, skill in sorted(skills.items()):
        print(f"  - {name}: {skill.description}")

    print("\n" + "-" * 50)
    print("Instructions for LLM:")
    print("-" * 50)
    print(loader.generate_instructions())

    print("\n" + "-" * 50)
    print("Testing tool calls:")
    print("-" * 50)

    client = SkillsClient()

    tools_result = client.list_tools()
    print(f"\nAvailable tools: {len(tools_result.tools)}")
    for tool in tools_result.tools:
        print(f"  - {tool.name}")

    if skills:
        first_skill_name = sorted(skills.keys())[0]
        print(f"\nLoading skill: {first_skill_name}")
        result = client.call_tool("loadSkill", {"name": first_skill_name})
        print(f"\nResult:")
        print(result.content[0].text)


if __name__ == "__main__":
    main()
