"""
Example of using MCP Tools in Python.

This demonstrates how to use the MCP tool system
that mirrors goose-rs' tool architecture.
"""

import asyncio
import json
from pathlib import Path

# Import MCP tools
from src.assistant.mcp import (
    get_builtin_tool,
    list_tool_names,
    get_builtin_tools_info,
)

# Import tool classes directly if needed
from src.assistant.mcp.builtin_tools import (
    ShellTool,
    ReadFileTool,
    WriteFileTool,
)


async def main():
    """Main example function."""
    print("=" * 60)
    print("MCP Tools Example - Python Implementation")
    print("=" * 60)

    # 1. List all available tools
    print("\n1. Available Tools:")
    print("-" * 60)
    tool_names = list_tool_names()
    for i, name in enumerate(tool_names, 1):
        print(f"   {i}. {name}")

    # 2. Get tool information
    print("\n2. Tool Schemas:")
    print("-" * 60)
    tools_info = get_builtin_tools_info()
    for tool in tools_info:
        print(f"\n   Tool: {tool['name']}")
        print(f"   Description: {tool['description']}")
        print(f"   Schema: {json.dumps(tool['schema'], indent=4)[:200]}...")

    # 3. Execute shell tool
    print("\n3. Executing Shell Tool:")
    print("-" * 60)
    shell_tool = get_builtin_tool("shell")
    result = await shell_tool.run({"command": "echo 'Hello from MCP Python!'"})
    print(f"   Result: {result}")

    # 4. Execute read_file tool
    print("\n4. Reading File:")
    print("-" * 60)

    # First create a test file
    write_tool = get_builtin_tool("write_file", config={"memory_dir": ".test_memory"})
    await write_tool.run({
        "path": "test_file.txt",
        "content": "This is a test file created by MCP tools!",
        "create_dirs": True
    })

    # Now read it
    read_tool = get_builtin_tool("read_file")
    result = await read_tool.run({"path": "test_file.txt"})
    print(f"   Content: {result}")

    # 5. Execute search_files tool
    print("\n5. Searching Files:")
    print("-" * 60)
    search_tool = get_builtin_tool("search_files")
    result = await search_tool.run({
        "pattern": "test",
        "path": ".",
        "search_content": False
    })
    print(f"   Found files: {json.dumps(result, indent=2)[:300]}...")

    # 6. Execute remember_memory tool
    print("\n6. Storing Memory:")
    print("-" * 60)
    memory_tool = get_builtin_tool("remember_memory", config={"memory_dir": ".test_memory"})
    result = await memory_tool.run({
        "category": "demo",
        "data": "User prefers Python for development",
        "tags": ["preferences", "development"],
        "is_global": False
    })
    print(f"   Result: {result}")

    # 7. Retrieve memories
    print("\n7. Retrieving Memories:")
    print("-" * 60)
    retrieve_tool = get_builtin_tool("retrieve_memories", config={"memory_dir": ".test_memory"})
    result = await retrieve_tool.run({
        "category": "demo",
        "is_global": False
    })
    print(f"   Memories: {json.dumps(result, indent=2)[:300]}...")

    # 8. List directory
    print("\n8. Listing Directory:")
    print("-" * 60)
    list_tool = get_builtin_tool("list_directory")
    result = await list_tool.run({"path": "."})
    print(f"   Directory contents: {json.dumps(result, indent=2)[:300]}...")

    # Cleanup
    print("\n9. Cleanup:")
    print("-" * 60)
    test_file = Path("test_file.txt")
    if test_file.exists():
        test_file.unlink()
        print("   Deleted test_file.txt")

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
