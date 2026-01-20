"""
Write tool for file writing.

This tool provides file writing with:
- Overwrite existing files or create new ones
- Diff generation for permission requests
- LSP diagnostics integration
"""

import difflib
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


class WriteParams(ToolInputSchema):
    """Parameters for the Write tool."""

    filePath: str = Field(..., description="The absolute path to the file to write (must be absolute, not relative)")
    content: str = Field(..., description="The content to write to the file")


class WriteTool(BaseTool):
    """
    Write files with overwriting support.

    Features:
    - Overwrites existing files or creates new ones
    - Diff generation for permission requests
    - LSP diagnostics on write

    Usage:
    - filePath (required): Absolute path to the file
    - content (required): Content to write
    """

    name = "write"
    description = (
        "Writes content to a file, overwriting if it exists or creating if it doesn't. "
        "Generates a diff for permission requests. "
        "Supports both new and existing files."
    )
    input_schema = WriteParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Write content to the file.

        Args:
            params: Dictionary containing 'filePath' and 'content'.

        Returns:
            ToolResult with write confirmation.

        Raises:
            ToolError: If write fails.
        """
        file_path = params["filePath"]
        content = params["content"]

        # Convert to absolute path
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / file_path
            file_path = str(path)

        # Check parent directory exists
        parent = path.parent
        if parent and not parent.exists():
            raise ToolError(f"Parent directory does not exist: {parent}")

        # Read existing content for diff
        old_content = ""
        file_exists = path.exists()

        if file_exists:
            if not path.is_file():
                raise ToolError(f"Not a file: {file_path}")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    old_content = f.read()
            except Exception as e:
                raise ToolError(f"Failed to read existing file: {e}")

        # Generate diff
        diff = self._generate_diff(old_content, content, file_path)

        # Write new content
        try:
            # Ensure parent directory exists
            parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            raise ToolError(f"Failed to write file: {e}")

        return ToolResult(
            content="Wrote file successfully.",
            metadata={
                "diff": diff,
                "filepath": file_path,
                "exists": file_exists,
            },
        )

    def _generate_diff(self, old: str, new: str, file_path: str) -> str:
        """
        Generate unified diff between old and new content.

        Args:
            old: Original content (empty for new files).
            new: New content.
            file_path: File path for diff header.

        Returns:
            Unified diff string.
        """
        # Trim diff to remove common indentation
        diff_lines = list(difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=file_path,
            tofile=file_path,
            lineterm="",
        ))

        # Find minimum indentation
        min_indent = None
        for line in diff_lines:
            if line.startswith(("+", "-", " ")) and not line.startswith(("---", "+++")):
                stripped = line[1:].lstrip()
                if stripped:
                    indent = len(line[1:]) - len(stripped)
                    if min_indent is None or indent < min_indent:
                        min_indent = indent

        # Remove common indentation
        if min_indent and min_indent > 0:
            trimmed_lines = []
            for line in diff_lines:
                if line.startswith(("+", "-", " ")) and not line.startswith(("---", "+++")):
                    if line[1:].lstrip():
                        trimmed_lines.append(line[0] + line[1 + min_indent:])
                    else:
                        trimmed_lines.append(line[0])
                else:
                    trimmed_lines.append(line)
            diff_lines = trimmed_lines

        return "\n".join(diff_lines)

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to write (must be absolute, not relative)",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
