"""
Batch tool for parallel tool execution.

This tool provides:
- Execute multiple tools in parallel (up to 10)
- Disallow nested batch calls
- Filter out MCP/environment tools
- Aggregate results
"""

import asyncio
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult
from ..registry import get_registry


# Tools not allowed in batch (recursive prevention)
DISALLOWED = {"batch"}
# Tools filtered from suggestions (external tools)
FILTERED_FROM_SUGGESTIONS = {"invalid", "patch"}


class ToolCall(BaseModel):
    """A single tool call in the batch."""

    tool: str = Field(..., description="The name of the tool to execute")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the tool",
    )


class BatchParams(ToolInputSchema):
    """Parameters for the Batch tool."""

    tool_calls: List[ToolCall] = Field(
        ...,
        min_length=1,
        description="Array of tool calls to execute in parallel",
    )


class BatchTool(Tool):
    """
    Execute multiple tools in parallel.

    Features:
    - Parallel execution of up to 10 tools
    - Disallow nested batch calls
    - Filter out MCP/environment tools
    - Aggregate results

    Usage:
    - tool_calls (required): Array of {tool: string, parameters: object}
    """

    name = "batch"
    description = (
        "Execute multiple tools in parallel for optimal performance. "
        "Maximum 10 tools per batch. "
        "Disallows nested batch calls to prevent recursion. "
        "Filters out external tools (MCP, environment) that cannot be batched."
    )
    input_schema = BatchParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._max_calls = self.config.get("max_calls", 10)
        self._session_id = self.config.get("session_id", "default")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the batch tool calls.

        Args:
            params: Dictionary containing 'tool_calls' array.

        Returns:
            ToolResult with aggregated results.

        Raises:
            ToolError: If batch validation fails or execution error occurs.
        """
        tool_calls = params["tool_calls"]

        # Limit to max calls
        if len(tool_calls) > self._max_calls:
            tool_calls = tool_calls[:self._max_calls]

        # Validate each tool call
        registry = get_registry()
        available_tools = registry.ids()

        for call in tool_calls:
            tool_name = call.tool

            # Check for disallowed tools
            if tool_name in DISALLOWED:
                raise ToolError(
                    f"Tool '{tool_name}' is not allowed in batch. "
                    f"Disallowed tools: {', '.join(DISALLOWED)}"
                )

            # Check if tool exists
            if tool_name not in available_tools:
                filtered = [
                    t for t in available_tools
                    if t not in FILTERED_FROM_SUGGESTIONS
                ]
                raise ToolError(
                    f"Tool '{tool_name}' not in registry. "
                    f"External tools (MCP, environment) cannot be batched. "
                    f"Available tools: {', '.join(filtered)}"
                )

        # Execute all tool calls in parallel
        results = await self._execute_parallel(tool_calls)

        # Count successful/failed
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        if failed > 0:
            output = f"Executed {successful}/{len(results)} tools successfully. {failed} failed."
        else:
            output = f"All {successful} tools executed successfully.\n\nKeep using batch tool for optimal performance in your next response!"

        # Collect attachments from successful results
        attachments = []
        for result in results:
            if result.get("success") and result.get("result"):
                attachments.extend(result["result"].get("attachments", []))

        return ToolResult(
            content=output,
            metadata={
                "total_calls": len(results),
                "successful": successful,
                "failed": failed,
                "tools": [call.tool for call in params["tool_calls"][:len(results)]],
                "details": results,
            },
        )

    async def _execute_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Execute tool calls in parallel.

        Args:
            tool_calls: List of tool call dictionaries.

        Returns:
            List of result dictionaries.
        """
        registry = get_registry()

        async def execute_single(call: Dict[str, Any]) -> Dict[str, Any]:
            """Execute a single tool call."""
            tool_name = call["tool"]
            tool_params = call.get("parameters", {})

            try:
                tool = registry.get_instance(tool_name, {"session_id": self._session_id})
                result = await tool.run(tool_params)

                return {
                    "success": True,
                    "tool": tool_name,
                    "result": result.to_dict() if hasattr(result, "to_dict") else {
                        "content": result.content,
                        "error": result.error,
                        "state": result.state.value,
                        "metadata": result.metadata,
                    },
                }
            except Exception as e:
                return {
                    "success": False,
                    "tool": tool_name,
                    "error": str(e),
                }

        # Execute all in parallel
        return await asyncio.gather(
            *[execute_single(call) for call in tool_calls],
            return_exceptions=True,
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "tool_calls": {
                "type": "array",
                "description": "Array of tool calls to execute in parallel",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": "The name of the tool to execute",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Parameters for the tool",
                        },
                    },
                },
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
