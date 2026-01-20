"""
Grep tool for regex pattern searching in files.

This tool provides regex pattern search:
- Full regex support for pattern matching
- File include filtering (e.g., *.js, *.{ts,tsx})
- Max 100 results with truncation warning
- Output format: `Line {lineNum}: {text}`
- Results sorted by modification time (newest first)
"""

import os
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


MAX_LINE_LENGTH = 2000
MAX_RESULTS = 100


class GrepParams(ToolInputSchema):
    """Parameters for the Grep tool."""

    pattern: str = Field(..., description="The regex pattern to search for in file contents")
    path: Optional[str] = Field(
        None,
        description="The directory to search in. Defaults to current working directory.",
    )
    include: Optional[str] = Field(
        None,
        description='File pattern to include in search (e.g. "*.js", "*.{ts,tsx}")',
    )


class GrepMatch:
    """Represents a grep match result."""

    def __init__(self, path: str, mod_time: float, line_num: int, line_text: str):
        self.path = path
        self.mod_time = mod_time
        self.line_num = line_num
        self.line_text = line_text


class GrepTool(BaseTool):
    """
    Regex pattern search in file contents.

    Features:
    - Full regex support for pattern matching
    - File include filtering (e.g., *.js, *.{ts,tsx})
    - Max 100 results with truncation warning
    - Output format: `Line {lineNum}: {text}`
    - Results sorted by modification time (newest first)

    Usage:
    - pattern (required): Regex pattern to search for
    - path (optional): Directory to search (defaults to current directory)
    - include (optional): File pattern to include (e.g., "*.js", "*.{ts,tsx}")
    """

    name = "grep"
    description = (
        "Regex pattern search in file contents. Supports full regex syntax. "
        "Results are sorted by modification time (newest first). "
        "Returns up to 100 matches with a warning if more files match. "
        "Can filter by file pattern (e.g., *.js, *.{ts,tsx})."
    )
    input_schema = GrepParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._default_directory = self.config.get("directory", str(Path.cwd()))
        self._ripgrep_available = None  # Cache ripgrep availability

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the grep search.

        Args:
            params: Dictionary containing 'pattern', optional 'path', and 'include'.

        Returns:
            ToolResult with matching lines.

        Raises:
            ToolError: If directory doesn't exist or search fails.
        """
        pattern = params["pattern"]
        if not pattern:
            raise ToolError("pattern is required")

        search_path = params.get("path", self._default_directory)

        # Convert to absolute path
        path = Path(search_path)
        if not path.is_absolute():
            path = Path.cwd() / search_path

        if not path.exists():
            raise ToolError(f"Directory not found: {path}")

        if not path.is_dir():
            raise ToolError(f"Not a directory: {path}")

        include = params.get("include")

        # Try to use ripgrep if available (much faster)
        if self._is_ripgrep_available():
            return await self._grep_with_ripgrep(pattern, path, include)

        # Fallback to Python implementation
        return await self._grep_with_python(pattern, path, include)

    def _is_ripgrep_available(self) -> bool:
        """
        Check if ripgrep (rg) is available.

        Returns:
            True if ripgrep is available.
        """
        if self._ripgrep_available is not None:
            return self._ripgrep_available

        self._ripgrep_available = shutil.which("rg") is not None
        return self._ripgrep_available

    async def _grep_with_ripgrep(
        self,
        pattern: str,
        search_path: Path,
        include: Optional[str],
    ) -> ToolResult:
        """
        Perform grep search using ripgrep.

        Args:
            pattern: Regex pattern.
            search_path: Directory to search.
            include: Optional file include pattern.

        Returns:
            ToolResult with matches.
        """
        try:
            args = [
                "rg",
                "-nH",
                "--hidden",
                "--follow",
                "--no-messages",
                "--field-match-separator=|",
                "--regexp",
                pattern,
            ]

            if include:
                args.extend(["--glob", include])

            args.append(str(search_path))

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Exit codes: 0 = matches found, 1 = no matches, 2 = errors
            if result.returncode == 1 or (result.returncode == 2 and not result.stdout.strip()):
                return ToolResult(
                    content="No files found",
                    metadata={"matches": 0, "truncated": False},
                )

            if result.returncode != 0 and result.returncode != 2:
                raise ToolError(f"ripgrep failed: {result.stderr}")

            # Parse output
            matches = self._parse_ripgrep_output(result.stdout)

            if not matches:
                return ToolResult(
                    content="No files found",
                    metadata={"matches": 0, "truncated": False},
                )

            # Sort by modification time
            matches.sort(key=lambda x: x.mod_time, reverse=True)

            # Limit results
            truncated = len(matches) > MAX_RESULTS
            if truncated:
                matches = matches[:MAX_RESULTS]

            return self._format_matches(matches, truncated, pattern)

        except subprocess.TimeoutExpired:
            raise ToolError("Grep search timed out")
        except Exception as e:
            raise ToolError(f"Grep search failed: {e}")

    def _parse_ripgrep_output(self, output: str) -> List[GrepMatch]:
        """
        Parse ripgrep output.

        Args:
            output: Output from ripgrep command.

        Returns:
            List of GrepMatch objects.
        """
        matches: List[GrepMatch] = []
        lines = output.strip().split("\n")

        for line in lines:
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 3:
                continue

            file_path = parts[0]
            try:
                line_num = int(parts[1])
                line_text = "|".join(parts[2:])
            except (ValueError, IndexError):
                continue

            # Get modification time
            try:
                mod_time = Path(file_path).stat().st_mtime
            except (OSError, IOError):
                continue

            matches.append(GrepMatch(file_path, mod_time, line_num, line_text))

        return matches

    async def _grep_with_python(
        self,
        pattern: str,
        search_path: Path,
        include: Optional[str],
    ) -> ToolResult:
        """
        Perform grep search using Python (fallback).

        Args:
            pattern: Regex pattern.
            search_path: Directory to search.
            include: Optional file include pattern.

        Returns:
            ToolResult with matches.
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"Invalid regex pattern: {e}")

        matches: List[GrepMatch] = []

        # Walk directory tree
        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                # Apply include filter
                if include and not self._matches_include(filename, include):
                    continue

                file_path = Path(root) / filename

                # Skip hidden files (ripgrep includes them, but we'll be consistent)
                # if filename.startswith('.'):
                #     continue

                try:
                    # Get modification time
                    mod_time = file_path.stat().st_mtime

                    # Read and search file
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                matches.append(
                                    GrepMatch(str(file_path), mod_time, line_num, line.rstrip("\n\r"))
                                )

                    # Limit total matches to avoid too much data
                    if len(matches) > MAX_RESULTS * 2:
                        break

                except (OSError, IOError, UnicodeDecodeError):
                    pass

            if len(matches) > MAX_RESULTS * 2:
                break

        if not matches:
            return ToolResult(
                content="No files found",
                metadata={"matches": 0, "truncated": False},
            )

        # Sort by modification time
        matches.sort(key=lambda x: x.mod_time, reverse=True)

        # Limit results
        truncated = len(matches) > MAX_RESULTS
        if truncated:
            matches = matches[:MAX_RESULTS]

        return self._format_matches(matches, truncated, pattern)

    def _matches_include(self, filename: str, include: str) -> bool:
        """
        Check if filename matches the include pattern.

        Args:
            filename: The filename to check.
            include: The include pattern (e.g., "*.js", "*.{ts,tsx}").

        Returns:
            True if filename matches.
        """
        # Handle brace expansion like *.{ts,tsx}
        if include.startswith("*.{") and include.endswith("}"):
            extensions = include[3:-1].split(",")
            base = filename.rsplit(".", 1)
            if len(base) == 2:
                return f".{base[1]}" in extensions
            return False

        # Simple glob pattern
        return fnmatch(filename, include)

    def _format_matches(
        self,
        matches: List[GrepMatch],
        truncated: bool,
        pattern: str,
    ) -> ToolResult:
        """
        Format matches for output.

        Args:
            matches: List of GrepMatch objects.
            truncated: Whether results were truncated.
            pattern: The search pattern.

        Returns:
            Formatted ToolResult.
        """
        output_lines = [f"Found {len(matches)} matches"]

        current_file = ""
        for match in matches:
            if current_file != match.path:
                if current_file != "":
                    output_lines.append("")
                current_file = match.path
                output_lines.append(f"{match.path}:")

            truncated_line = (
                match.line_text[:MAX_LINE_LENGTH] + "..."
                if len(match.line_text) > MAX_LINE_LENGTH
                else match.line_text
            )
            output_lines.append(f"  Line {match.line_num}: {truncated_line}")

        if truncated:
            output_lines.extend([
                "",
                "(Results are truncated. Consider using a more specific path or pattern.)"
            ])

        return ToolResult(
            content="\n".join(output_lines),
            metadata={
                "matches": len(matches),
                "truncated": truncated,
            },
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to search for in file contents",
            },
            "path": {
                "type": "string",
                "description": "The directory to search in. Defaults to current working directory.",
            },
            "include": {
                "type": "string",
                "description": 'File pattern to include in search (e.g. "*.js", "*.{ts,tsx}")',
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
