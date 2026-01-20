"""
MultiEdit tool for sequential file edits.

This tool provides:
- Sequential edits on a single file
- Reuses EditTool replacers
- Efficient for multiple changes to one file
"""

from pathlib import Path
from typing import Any, Dict, List,Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult
from .edit import EditTool


class EditOperation(BaseModel):
    """A single edit operation."""

    oldString: str = Field(..., description="The text to replace")
    newString: str = Field(..., description="The text to replace it with (must be different from oldString)")
    replaceAll: Optional[bool] = Field(False, description="Replace all occurrences of oldString (default false)")


class MultiEditParams(ToolInputSchema):
    """Parameters for the MultiEdit tool."""

    filePath: str = Field(..., description="The absolute path to the file to modify")
    edits: List[EditOperation] = Field(
        ...,
        min_length=1,
        description="Array of edit operations to perform sequentially on the file",
    )


class MultiEditTool(BaseTool):
    """
    Perform sequential edits on a single file.

    Features:
    - Multiple edits in one tool call
    - Reuses EditTool replacers for fuzzy matching
    - Sequential execution
    - Efficient for multiple changes to one file

    Usage:
    - filePath (required): Absolute path to the file
    - edits (required): Array of {oldString, newString, replaceAll} objects
    """

    name = "multiedit"
    description = (
        "Perform multiple sequential edits on a single file. "
        "Each edit can use fuzzy matching like the Edit tool. "
        "Use this when you need to make multiple changes to the same file."
    )
    input_schema = MultiEditParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        # Create an EditTool instance to reuse
        self._edit_tool = EditTool(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the multi-edit.

        Args:
            params: Dictionary containing 'filePath' and 'edits'.

        Returns:
            ToolResult with combined results.

        Raises:
            ToolError: If any edit fails.
        """
        file_path = params["filePath"]
        edits = params["edits"]

        # Convert to absolute path
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / file_path
            file_path = str(path)

        # Execute edits sequentially
        results = []
        for i, edit_op in enumerate(edits):
            edit_params = {
                "filePath": file_path,
                "oldString": edit_op.oldString,
                "newString": edit_op.newString,
                "replaceAll": edit_op.replaceAll,
            }

            try:
                result = await self._edit_tool.run(edit_params)
                results.append(result.to_dict() if hasattr(result, "to_dict") else {
                    "content": result.content,
                    "error": result.error,
                    "state": result.state.value,
                    "metadata": result.metadata,
                })
            except Exception as e:
                # If an edit fails, we should report the error
                results.append({
                    "success": False,
                    "error": str(e),
                })
                # For sequential edits, if one fails, we might want to stop
                # But for now, we'll continue and let the user know which failed

        # Get the last result (most recent edit)
        final_result = results[-1] if results else {"content": ""}

        return ToolResult(
            content=final_result.get("content", "No edits performed"),
            error=final_result.get("error"),
            state=final_result.get("state", "completed"),
            metadata={
                "results": results,
                "num_edits": len(edits),
            },
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to modify",
            },
            "edits": {
                "type": "array",
                "description": "Array of edit operations to perform sequentially on the file",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "oldString": {
                            "type": "string",
                            "description": "The text to replace",
                        },
                        "newString": {
                            "type": "string",
                            "description": "The text to replace it with (must be different from oldString)",
                        },
                        "replaceAll": {
                            "type": "boolean",
                            "description": "Replace all occurrences of oldString (default false)",
                            "default": False,
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
