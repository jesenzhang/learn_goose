"""
Example demonstrating the Unified Tool System.

This example shows how to use the combined features from
goose-py and pho toolkits in a single system.
"""

import asyncio
import json
from pathlib import Path

# Import the unified toolkit
from assistant.unified_toolkit import (
    # Core classes
    BaseTool, ToolInputSchema, register_tool_class,

    # Registration functions
    register_tool, get_global_registry,

    # Execution
    execute_tool, ExecutionContext, ToolExecutor,

    # Initialization
    initialize_toolkit,
)


# ============================================================================
# Example Tool Implementations
# ============================================================================

# Example 1: Class-based tool (from goose-py)
class CalculatorTool(BaseTool):
    """A calculator tool demonstrating class-based registration."""

    name = "calculator"
    description = "Perform basic arithmetic operations"
    category = "math"

    class Params(ToolInputSchema):
        operation: str  # "add", "subtract", "multiply", "divide"
        a: float
        b: float

    input_schema = Params

    async def execute(self, params: Params) -> str:
        """Execute the calculator operation."""
        if params.operation == "add":
            result = params.a + params.b
        elif params.operation == "subtract":
            result = params.a - params.b
        elif params.operation == "multiply":
            result = params.a * params.b
        elif params.operation == "divide":
            if params.b == 0:
                raise ValueError("Cannot divide by zero")
            result = params.a / params.b
        else:
            raise ValueError(f"Unknown operation: {params.operation}")

        return f"{params.a} {params.operation} {params.b} = {result}"


# Example 2: Function-based tool (from pho)
@register_tool(
    name="string_processor",
    description="Process strings with various operations",
    category="text"
)
def string_processor(
    text: str,
    operation: str = "uppercase",  # "uppercase", "lowercase", "reverse", "count"
    ctx: ExecutionContext = None  # Context injection (from pho)
) -> str:
    """
    Process strings with various operations.

    Demonstrates context injection and function-based tools.
    """
    # Log context if available (demonstrates pho-style context injection)
    if ctx and ctx.session_id:
        print(f"Processing text in session: {ctx.session_id}")

    if operation == "uppercase":
        result = text.upper()
    elif operation == "lowercase":
        result = text.lower()
    elif operation == "reverse":
        result = text[::-1]
    elif operation == "count":
        result = str(len(text))
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return f"Result: {result}"


# Example 3: File operation tool (combines both approaches)
class FileOperationsTool(BaseTool):
    """File operations tool demonstrating advanced features."""

    name = "file_ops"
    description = "Perform file operations"
    category = "file"

    class Params(ToolInputSchema):
        operation: str  # "read", "write", "exists", "list"
        path: str
        content: str = ""  # For write operations
        create_dirs: bool = False

    input_schema = Params

    async def execute(self, params: Params) -> str:
        """Execute file operations."""
        path = Path(params.path)

        if params.operation == "read":
            if not path.exists():
                raise FileNotFoundError(f"File not found: {params.path}")
            return path.read_text(encoding="utf-8")

        elif params.operation == "write":
            if params.create_dirs:
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(params.content, encoding="utf-8")
            return f"Written {len(params.content)} bytes to {params.path}"

        elif params.operation == "exists":
            exists = path.exists()
            return f"Path '{params.path}' {'exists' if exists else 'does not exist'}"

        elif params.operation == "list":
            if not path.is_dir():
                raise NotADirectoryError(f"Not a directory: {params.path}")
            items = [str(item) for item in path.iterdir()]
            return f"Directory contents: {', '.join(items)}"

        else:
            raise ValueError(f"Unknown operation: {params.operation}")


# ============================================================================
# Main Demonstration
# ============================================================================

async def main():
    """Main demonstration function."""
    print("=" * 80)
    print("UNIFIED TOOL SYSTEM DEMONSTRATION")
    print("=" * 80)

    # Initialize the toolkit
    print("\n1. Initializing toolkit...")
    initialize_toolkit()

    # Register our custom tools
    print("2. Registering custom tools...")
    register_tool_class(CalculatorTool)
    register_tool_class(FileOperationsTool)

    # Get registry for inspection
    registry = get_global_registry()

    # Show registered tools
    print("\n3. Registered Tools:")
    print("-" * 40)
    for name, metadata in registry.list_all().items():
        print(f"   • {name}: {metadata.description}")
        print(f"     Category: {metadata.category or 'None'}")
        print(f"     Type: {metadata.source_type.value}")

    # Demonstrate tool execution
    print("\n4. Executing Tools:")
    print("-" * 40)

    # Calculator tool
    print("\n   Calculator Tool:")
    result = await execute_tool("calculator", operation="add", a=10, b=5)
    print(f"   Result: {result.result}")
    print(f"   Status: {result.status.value}")
    print(".3f")

    # String processor tool
    print("\n   String Processor Tool:")
    context = ExecutionContext(
        session_id="demo_session_123",
        user_id="demo_user_456"
    )
    result = await execute_tool("string_processor", text="Hello World", operation="reverse")
    print(f"   Result: {result.result}")

    # File operations
    print("\n   File Operations Tool:")

    # Create a test file
    result = await execute_tool("file_ops",
                              operation="write",
                              path="demo_test.txt",
                              content="This is a test file created by the unified toolkit!",
                              create_dirs=False)
    print(f"   Write result: {result.result}")

    # Read the file back
    result = await execute_tool("file_ops", operation="read", path="demo_test.txt")
    print(f"   Read result: {result.result}")

    # Check if file exists
    result = await execute_tool("file_ops", operation="exists", path="demo_test.txt")
    print(f"   Exists check: {result.result}")

    # Clean up
    Path("demo_test.txt").unlink(missing_ok=True)

    # Show registry statistics
    print("\n5. Registry Statistics:")
    print("-" * 40)
    stats = registry.get_statistics()
    print(json.dumps(stats, indent=2))

    # Demonstrate format exports
    print("\n6. Format Exports:")
    print("-" * 40)

    print("\n   OpenAI Functions:")
    openai_funcs = registry.to_openai_functions()
    for func in openai_funcs[:3]:  # Show first 3
        print(f"   • {func['name']}: {func['description'][:50]}...")

    print("\n   MCP Tools:")
    mcp_tools = registry.to_mcp_tools()
    for tool in mcp_tools[:3]:  # Show first 3
        print(f"   • {tool['name']}: {tool['description'][:50]}...")

    # Demonstrate advanced executor features
    print("\n7. Advanced Executor Features:")
    print("-" * 40)

    executor = ToolExecutor(registry, enable_cache=True)

    # Execute with context
    context = ExecutionContext(
        session_id="advanced_demo",
        variables={"debug": True}
    )

    # First execution (will be cached)
    print("\n   First execution (uncached):")
    result1 = await executor.execute("calculator", {"operation": "multiply", "a": 6, "b": 7}, context)
    print(f"   Result: {result1.result}")
    print(f"   Cached: {result1.cached}")

    # Second execution (should be cached)
    print("\n   Second execution (should be cached):")
    result2 = await executor.execute("calculator", {"operation": "multiply", "a": 6, "b": 7}, context)
    print(f"   Result: {result2.result}")
    print(f"   Cached: {result2.cached}")

    print(f"\n   Cache size: {executor.get_cache_size()}")

    # Demonstrate error handling
    print("\n8. Error Handling:")
    print("-" * 40)

    try:
        result = await execute_tool("calculator", operation="divide", a=10, b=0)
    except Exception as e:
        print(f"   Caught error: {e}")

    # Try non-existent tool
    result = await execute_tool("non_existent_tool", param="value")
    print(f"   Non-existent tool result: {result.status.value} - {result.error}")

    print("\n" + "=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())