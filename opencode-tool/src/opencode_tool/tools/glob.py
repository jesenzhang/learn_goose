"""
Glob tool for file pattern matching.

This tool provides file pattern matching using glob patterns:
- Supports standard glob patterns (**, *, ?, etc.)
- Returns results sorted by modification time (newest first)
- Limit: 100 files max with truncation warning
- Can search in specific directory or current directory
"""

import os
import time
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult


class GlobParams(ToolInputSchema):
    """Parameters for the Glob tool."""

    pattern: str = Field(..., description="The glob pattern to match files against")
    path: Optional[str] = Field(
        None,
        description=(
            "The directory to search in. If not specified, the current working directory "
            "will be used. IMPORTANT: Omit this field to use the default directory. "
            "DO NOT enter 'undefined' or 'null' - simply omit it for default behavior."
        ),
    )


class GlobTool(Tool):
    """
    File pattern matching using glob patterns.

    Features:
    - Supports standard glob patterns (**, *, ?, etc.)
    - Results sorted by modification time (newest first)
    - Limit: 100 files max
    - Truncation warning when more files match
    - Can search in specific directory or current directory

    Usage:
    - pattern (required): Glob pattern (e.g., "*.py", "**/*.ts", "src/**/*.js")
    - path (optional): Directory to search (defaults to current directory)
    """

    name = "glob"
    description = (
        "File pattern matching using glob patterns. Supports patterns like ** (recursive), "
        "* (wildcard), ? (single character), etc. Results are sorted by "
        "modification time (newest first). Returns up to 100 files with a warning "
        "if more files match."
    )
    input_schema = GlobParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._default_directory = self.config.get("directory", str(Path.cwd()))
        self._limit = self.config.get("limit", 100)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the glob pattern matching.

        Args:
            params: Dictionary containing 'pattern' and optional 'path'.

        Returns:
            ToolResult with matching file paths.

        Raises:
            ToolError: If directory doesn't exist or search fails.
        """
        pattern = params["pattern"]
        search_path = params.get("path", self._default_directory)

        # Convert to absolute path
        path = Path(search_path)
        if not path.is_absolute():
            path = Path.cwd() / search_path

        if not path.exists():
            raise ToolError(f"Directory not found: {path}")

        if not path.is_dir():
            raise ToolError(f"Not a directory: {path}")

        # Perform glob search
        try:
            files = self._glob_search(pattern, path)

            if not files:
                return ToolResult(
                    content="No files found",
                    metadata={"count": 0, "truncated": False},
                )

            # Sort by modification time (newest first)
            files = sorted(files, key=lambda x: x[1], reverse=True)

            # Extract paths (drop mtime)
            file_paths = [str(p) for p, _ in files]

            # Check for truncation
            truncated = len(files) >= self._limit
            output_lines = file_paths.copy()

            if truncated:
                output_lines.extend([
                    "",
                    "(Results are truncated. Consider using a more specific path or pattern.)"
                ])

            return ToolResult(
                content="\n".join(output_lines),
                metadata={
                    "count": len(files),
                    "truncated": truncated,
                },
            )
        except Exception as e:
            raise ToolError(f"Glob search failed: {e}")

    def _glob_search(
        self,
        pattern: str,
        search_path: Path,
    ) -> List[tuple[Path, float]]:
        """
        Perform glob pattern matching.

        Args:
            pattern: The glob pattern.
            search_path: Directory to search in.

        Returns:
            List of (path, mtime) tuples.
        """
        files: List[tuple[Path, float]] = []

        # Convert glob pattern to something fnmatch can use
        # Handle ** for recursive matching
        if pattern.startswith("**/"):
            # Recursive pattern
            sub_pattern = pattern[3:]
            for root, dirs, filenames in os.walk(search_path):
                for filename in filenames:
                    if fnmatch(filename, sub_pattern):
                        full_path = Path(root) / filename
                        try:
                            mtime = full_path.stat().st_mtime
                            files.append((full_path, mtime))
                        except (OSError, IOError):
                            pass
        else:
            # Non-recursive pattern
            if "**" in pattern:
                # Complex pattern with ** in the middle
                for root, dirs, filenames in os.walk(search_path):
                    rel_path = root.relative_to(search_path)
                    for filename in filenames:
                        full_path = Path(root) / filename
                        rel_str = str(rel_path / filename) if rel_path else filename
                        if fnmatch(rel_str, pattern):
                            try:
                                mtime = full_path.stat().st_mtime
                                files.append((full_path, mtime))
                            except (OSError, IOError):
                                pass
            else:
                # Simple pattern in current directory
                for entry in search_path.iterdir():
                    if fnmatch(entry.name, pattern):
                        try:
                            mtime = entry.stat().st_mtime
                            files.append((entry, mtime))
                        except (OSError, IOError):
                            pass

        # Limit results
        if len(files) > self._limit:
            files = files[:self._limit]

        return files

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files against",
            },
            "path": {
                "type": "string",
                "description": (
                    "The directory to search in. If not specified, "
                    "the current working directory will be used."
                ),
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
