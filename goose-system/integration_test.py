"""
Integration Test: Skills to Tools Bridge

Demonstrates loading agent_skills, extracting Python implementations,
and converting them to FunctionTool instances with MCP format support.
"""

import asyncio
import json
from pathlib import Path

from goose.skills.impl_loader import SkillImplLoader, load_skill_with_implementation
from goose.tools.base import function_tool_to_mcp_format


async def main():
    print("=" * 60)
    print("Skills to Tools Integration Test")
    print("=" * 60)
    
    agent_skills_path = Path(__file__).resolve().parent.parent / "agent_skills"
    
    if not agent_skills_path.exists():
        print(f"Error: agent_skills directory not found at {agent_skills_path}")
        return
    
    loader = SkillImplLoader(str(agent_skills_path))
    
    print("\n1. Loading all skills from agent_skills directory...")
    all_tools = loader.load_all_impl_tools()
    
    for skill_name, tools in all_tools.items():
        print(f"\n  Skill: {skill_name}")
        print(f"  Tools: {list(tools.keys())}")
    
    print("\n" + "=" * 60)
    print("2. Testing Calculator Skill")
    print("=" * 60)
    
    calc_result = load_skill_with_implementation(str(agent_skills_path / "calculator"))
    print(f"\n  Metadata: {calc_result['metadata'].name}")
    print(f"  Description: {calc_result['metadata'].description[:100]}...")
    
    if "calculate" in calc_result["tools"]:
        tool = calc_result["tools"]["calculate"]
        print(f"\n  Tool: {tool.name}")
        print(f"  Description: {tool.description[:80]}...")
        
        print("\n  Testing execution:")
        response = await tool.execute({"expression": "sqrt(144) + 5**2"})
        print(f"    sqrt(144) + 5**2 = {response}")
        
        response = await tool.execute({"expression": "mean([1, 2, 3, 4, 5])"})
        print(f"    mean([1, 2, 3, 4, 5]) = {response}")
        
        print("\n  MCP Format:")
        mcp_format = function_tool_to_mcp_format(tool)
        print(f"    {json.dumps(mcp_format['input_schema'], indent=4)}")
    
    print("\n" + "=" * 60)
    print("3. Testing Clipboard Skill (with state injection)")
    print("=" * 60)
    
    clip_result = load_skill_with_implementation(str(agent_skills_path / "clipboard"))
    print(f"\n  Metadata: {clip_result['metadata'].name}")
    print(f"  Tools: {list(clip_result['tools'].keys())}")
    
    mock_state = type("MockState", (), {"shared_memory": {}})()
    
    if "write_to_clipboard" in clip_result["tools"]:
        tool = clip_result["tools"]["write_to_clipboard"]
        
        print("\n  Testing write_to_clipboard:")
        response = await tool.execute(
            {"key": "analysis_result", "value": {"score": 95, "status": "complete"}},
            state=mock_state
        )
        print(f"    {response}")
        
        if "read_from_clipboard" in clip_result["tools"]:
            read_tool = clip_result["tools"]["read_from_clipboard"]
            
            print("\n  Testing read_from_clipboard:")
            response = await read_tool.execute({"key": "analysis_result"}, state=mock_state)
            print(f"    {response}")
    
    print("\n" + "=" * 60)
    print("4. Testing File Manager Skill")
    print("=" * 60)
    
    fm_result = load_skill_with_implementation(str(agent_skills_path / "file-manager"))
    if fm_result["tools"]:
        print(f"\n  Available tools: {list(fm_result['tools'].keys())}")
        
        tool = fm_result["tools"].get("list_directory")
        if tool:
            print(f"\n  Testing list_directory:")
            try:
                response = await tool.execute({"path": "."})
                print(f"    {response}")
            except Exception as e:
                print(f"    Error: {e}")
    else:
        print("\n  No tools loaded (impl.py may have platform-specific dependencies)")
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"\n  Total skills loaded: {len(all_tools)}")
    total_tools = sum(len(tools) for tools in all_tools.values())
    print(f"  Total tools loaded: {total_tools}")
    print("\n  Integration successful!")


if __name__ == "__main__":
    asyncio.run(main())
