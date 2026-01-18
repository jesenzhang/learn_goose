# opencode-tool

Python implementation of OpenCode Agent Tools.

This package provides Python implementations of all the built-in tools from the OpenCode Agent system.

## Installation

```bash
cd opencode-tool
pip install -e .
```

Or from requirements.txt:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Tool Usage

```python
from opencode_tool import BashTool, ReadTool, EditTool

# Create and run a tool
bash_tool = BashTool()
result = await bash_tool.run({
    "command": "ls -la",
    "description": "List files in current directory"
})

print(result.content)
```

### Using the Registry

```python
from opencode_tool import get_registry, register_tool
from opencode_tool.tools import BashTool, ReadTool

# Get the registry
registry = get_registry()

# Register tools (automatically done on import)
registry.register(BashTool)
registry.register(ReadTool)

# List available tools
print(registry.ids())

# Get and run a tool
tool = registry.get_instance("bash")
result = await tool.run({
    "command": "echo hello",
    "description": "Say hello"
})
```

### Registering Custom Tools

```python
from opencode_tool import Tool, ToolInfo, register_tool
from pydantic import BaseModel, Field

class MyCustomParams(BaseModel):
    message: str = Field(..., description="The message to process")

class MyCustomTool(Tool):
    name = "my_custom_tool"
    description = "A custom tool for specific purposes"
    input_schema = MyCustomParams

    async def execute(self, params):
        return ToolResult(
            content=f"Processed: {params['message']}",
            metadata={},
        )

# Register the tool
register_tool(MyCustomTool, custom=True)
```

## Available Tools

| Tool | Description |
|-------|-------------|
| **bash** | Execute bash commands with timeout and external directory detection |
| **read** | Read files with line-based pagination, supports images/PDFs |
| **glob** | File pattern matching using glob patterns |
| **grep** | Regex pattern search in file contents |
| **edit** | Intelligent file editing with fuzzy matching strategies |
| **write** | Write/overwrite files with diff generation |
| **list** | Directory tree rendering with indentation |
| **websearch** | Web search via MCP (https://mcp.exa.ai) |
| **webfetch** | Fetch web content with HTML to markdown conversion |
| **todowrite** | Update the todo list |
| **todoread** | Read the current todo list |
| **task** | Launch subagents for specialized tasks |
| **skill** | Load custom skills from SKILL.md files |
| **batch** | Execute multiple tools in parallel |
| **codesearch** | Semantic code search via embeddings |
| **plan_enter** | Suggest switching to plan agent |
| **plan_exit** | Suggest switching to build agent |
| **multiedit** | Perform sequential edits on a single file |

## Project Structure

```
opencode-tool/
├── src/
│   └── opencode_tool/
│       ├── __init__.py
│       ├── tool.py           # Base Tool class and types
│       ├── registry.py       # Tool registry
│       └── tools/           # Tool implementations
│           ├── __init__.py
│           ├── bash.py
│           ├── read.py
│           ├── glob.py
│           ├── grep.py
│           ├── edit.py
│           ├── write.py
│           ├── ls.py
│           ├── websearch.py
│           ├── webfetch.py
│           ├── todo.py
│           ├── task.py
│           ├── skill.py
│           ├── batch.py
│           ├── codesearch.py
│           ├── plan.py
│           └── multiedit.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Development

```bash
# Install in development mode
pip install -e .

# Run tests
pytest tests/

# Format code
black src/
isort src/

# Type check
mypy src/
```

## License

MIT

## Original Reference

This implementation is based on the OpenCode Agent TypeScript implementation:
https://github.com/opencode/opencode
