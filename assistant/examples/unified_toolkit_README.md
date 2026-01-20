"""
README for the Unified Tool System.

This document explains the unified toolkit that combines the best
features from goose-py and pho tool systems.
"""

# ============================================================================
# Unified Tool System README
# ============================================================================

## Overview

The **Unified Tool System** combines the strengths of both `goose-py` and `pho` toolkits into a single, cohesive system:

### From goose-py:
- **System Integration**: Deep integration with the goose ecosystem
- **Standardization**: Consistent tool interfaces and metadata
- **OpenAI Compatibility**: Direct export to OpenAI function-calling format
- **Type Safety**: Strong typing with Pydantic models

### From pho:
- **Simplicity**: Easy-to-use registration decorators
- **Execution Features**: Advanced execution with context injection, caching, retries
- **Flexibility**: Support for multiple tool registration methods
- **Dependency Injection**: Rich execution context with service injection

## Key Features

### 1. Simple Registration
```python
# Decorator-based registration (from pho)
@register_tool("my_tool", description="Does something")
def my_tool(param: str) -> str:
    return f"Processed: {param}"

# Class-based registration (from goose-py)
class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something"

    class Params(ToolInputSchema):
        param: str

    input_schema = Params

    async def execute(self, params: Params) -> str:
        return f"Processed: {params.param}"

register_tool_class(MyTool)
```

### 2. Enhanced Execution
```python
# Execution with context and dependency injection
context = ExecutionContext(
    session_id="session_123",
    user_id="user_456",
    state=my_state,
    db=my_database
)

result = await execute_tool("my_tool", param="value")
# Result includes status, timing, caching info, etc.
```

### 3. Multiple Export Formats
```python
registry = get_global_registry()

# OpenAI function-calling format
openai_functions = registry.to_openai_functions()

# MCP tool format
mcp_tools = registry.to_mcp_tools()
```

### 4. Tool Categories and Organization
```python
# Tools are organized by category
tools_by_category = registry.list_by_category("file")
categories = registry.list_categories()
```

### 5. Advanced Features
- **Caching**: Automatic result caching with configurable TTL
- **Retries**: Configurable retry logic with backoff
- **Context Injection**: Automatic dependency injection
- **Statistics**: Registry statistics and monitoring
- **Type Safety**: Full Pydantic validation

## Architecture

### Core Components

1. **ToolMetadata**: Metadata for each registered tool
2. **UnifiedToolRegistry**: Central registry managing all tools
3. **ToolExecutor**: Advanced execution engine with context support
4. **BaseTool**: Abstract base class for tool implementations
5. **ExecutionContext**: Rich context for tool execution

### Tool Registration Types

- **BUILTIN**: Built-in tools (class-based)
- **DECORATOR**: Function tools registered via decorators
- **SKILL**: Tools loaded from skill directories
- **MCP**: Tools from MCP extensions

## Usage Examples

### Basic Usage
```python
from assistant.unified_toolkit import register_tool, execute_tool

@register_tool("echo", description="Echo a message")
def echo_tool(message: str) -> str:
    return f"Echo: {message}"

# Execute the tool
result = await execute_tool("echo", message="Hello World!")
print(result.result)  # "Echo: Hello World!"
```

### Advanced Usage
```python
from assistant.unified_toolkit import (
    BaseTool, ToolInputSchema, register_tool_class,
    ExecutionContext, get_global_executor
)

class FileTool(BaseTool):
    name = "file_operations"
    description = "File operations"
    category = "file"

    class Params(ToolInputSchema):
        operation: str  # "read" or "write"
        path: str
        content: Optional[str] = None

    input_schema = Params

    async def execute(self, params: Params) -> str:
        if params.operation == "read":
            return Path(params.path).read_text()
        elif params.operation == "write":
            Path(params.path).write_text(params.content or "")
            return f"Written to {params.path}"
        else:
            raise ValueError(f"Unknown operation: {params.operation}")

# Register and use
register_tool_class(FileTool)

# Execute with context
context = ExecutionContext(session_id="session_123")
executor = get_global_executor()
result = await executor.execute("file_operations", {
    "operation": "read",
    "path": "example.txt"
}, context)
```

## Integration Points

### With goose-py
- Compatible with `BaseRegistry` interface
- Supports `ToolDefinition` metadata
- Exports to OpenAI function format
- Integrates with goose conversation system

### With pho
- Supports `ExecutionContext` and dependency injection
- Includes `ToolExecutor` with advanced features
- Maintains decorator-based registration
- Supports inspector chains (future extension)

## Migration Guide

### From goose-py toolkit:
1. Replace `Tool` base class with `BaseTool`
2. Update imports from `goose.toolkit` to `assistant.unified_toolkit`
3. Use `register_tool_class()` instead of manual registry registration
4. Benefit from enhanced execution features automatically

### From pho toolkit:
1. Replace `ToolRegistry` with `UnifiedToolRegistry`
2. Update `ToolExecutor` usage (API is similar but enhanced)
3. Use `register_tool_class()` for class-based tools
4. Benefit from system integration automatically

## Performance Considerations

- **Caching**: Enabled by default, can be disabled per executor
- **Async Execution**: All tools run asynchronously
- **Thread Pool**: Sync functions run in thread pool automatically
- **Memory Management**: Registry uses efficient data structures

## Future Extensions

- **Inspector Chains**: Security and validation chains (from pho)
- **MCP Server Integration**: Native MCP server support
- **Skill Loading**: Automatic skill directory loading
- **Metrics**: Execution metrics and monitoring
- **Plugin System**: Dynamic plugin loading

## Testing

Run the example to test the unified toolkit:

```bash
cd /path/to/learn_goose/assistant
python examples/unified_toolkit_example.py
```

This demonstrates all major features and ensures the system works correctly.