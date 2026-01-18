"""
List tool for directory tree rendering.

This tool provides directory listing with:
- Directory tree rendering with indentation
- Ignore patterns for common directories
- Limit: 100 files max
- Truncated warning
"""

import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult


# Default ignore patterns
IGNORE_PATTERNS = [
    "node_modules/",
    "__pycache__/",
    ".git/",
    "dist/",
    "build/",
    "target/",
    "vendor/",
    "bin/",
    "obj/",
    ".idea/",
    ".vscode/",
    ".zig-cache/",
    "zig-out",
    ".coverage",
    "coverage/",
    "vendor/",
    "tmp/",
    "temp/",
    ".cache/",
    "cache/",
    "logs/",
    ".venv/",
    "venv/",
    "env/",
]

LIMIT = 100


class ListParams(ToolInputSchema):
    """Parameters for the List tool."""

    path: Optional[str] = Field(
        None,
        description="The absolute path to directory to list (must be absolute, not relative)",
    )
    ignore: Optional[List[str]] = Field(
        None,
        description="List of glob patterns to ignore",
    )


class ListTool(Tool):
    """
    Directory tree rendering with indentation.

    Features:
    - Directory tree rendering with indentation
    - Ignore patterns for common directories
    - Limit: 100 files max
    - Truncated warning

    Usage:
    - path (optional): Absolute path to directory (defaults to current directory)
    - ignore (optional): List of glob patterns to ignore
    """

    name = "list"
    description = (
        "Directory tree rendering with indentation. "
        "Shows subdirectories and files in a hierarchical format. "
        "Respects ignore patterns for common directories (node_modules, .git, etc.). "
        "Limited to 100 files with truncation warning."
    )
    input_schema = ListParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._default_directory = self.config.get("directory", str(Path.cwd()))

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the directory listing.

        Args:
            params: Dictionary containing optional 'path' and 'ignore'.

        Returns:
            ToolResult with directory tree.

        Raises:
            ToolError: If directory doesn't exist.
        """
        search_path = params.get("path", self._default_directory)
        ignore = params.get("ignore", [])

        # Convert to absolute path
        path = Path(search_path)
        if not path.is_absolute():
            path = Path.cwd() / search_path
            search_path = str(path)

        if not path.exists():
            raise ToolError(f"Directory not found: {path}")

        if not path.is_dir():
            raise ToolError(f"Not a directory: {path}")

        # Combine default ignores with custom ones
        ignore_patterns = IGNORE_PATTERNS.copy()
        if ignore:
            ignore_patterns.extend(ignore)

        # Collect files
        files = self._collect_files(path, ignore_patterns)

        if not files:
            return ToolResult(
                content=f"{search_path}/\n(Empty directory)",
                metadata={"count": 0, "truncated": False},
            )

        # Build directory structure
        output = f"{search_path}/\n"
        output += self._render_tree(files, path)

        truncated = len(files) >= LIMIT

        return ToolResult(
            content=output,
            metadata={
                "count": len(files),
                "truncated": truncated,
            },
        )

    def _collect_files(
        self,
        root: Path,
        ignore_patterns: List[str],
    ) -> List[str]:
        """
        Collect files from directory, respecting ignore patterns.

        Args:
            root: Root directory to search.
            ignore_patterns: List of glob patterns to ignore.

        Returns:
            List of relative file paths.
        """
        files: List[str] = []
        root_str = str(root)

        for dirpath, dirnames, filenames in os.walk(root_str):
            # Apply ignore patterns to directories
            dirnames[:] = [
                d for d in dirnames
                if not self._should_ignore(d, ignore_patterns, is_dir=True)
            ]

            # Collect files that aren't ignored
            for filename in filenames:
                if not self._should_ignore(filename, ignore_patterns):
                    full_path = os.path.join(dirpath, filename)
                    rel_path = os.path.relpath(full_path, root_str)
                    files.append(rel_path)

                    if len(files) >= LIMIT:
                        return files

        return files

    def _should_ignore(
        self,
        name: str,
        ignore_patterns: List[str],
        is_dir: bool = False,
    ) -> bool:
        """
        Check if a file/directory should be ignored.

        Args:
            name: Name of the file/directory.
            ignore_patterns: List of glob patterns.
            is_dir: Whether this is a directory.

        Returns:
            True if should be ignored.
        """
        # Check each pattern
        for pattern in ignore_patterns:
            # Handle directory patterns (ending with /)
            if pattern.endswith("/") and is_dir:
                if name == pattern[:-1] or fnmatch(name, pattern[:-1]):
                    return True
            # Handle regular patterns
            elif fnmatch(name, pattern):
                return True

        return False

    def _render_tree(self, files: List[str], root: Path) -> str:
        """
        Render directory tree with indentation.

        Args:
            files: List of relative file paths.
            root: Root directory path.

        Returns:
            Formatted tree string.
        """
        dirs: Set[str] = set()
        files_by_dir: Dict[str, List[str]] = {}

        # Collect directories and organize files
        for file in files:
            dir_path = os.path.dirname(file)
            if not dir_path:
                dir_path = "."

            # Add all parent directories
            parts = dir_path.split("/") if dir_path != "." else []
            for i in range(len(parts) + 1):
                dir_path_part = "." if i == 0 else "/".join(parts[:i])
                dirs.add(dir_path_part)

            # Add file to its directory
            if dir_path not in files_by_dir:
                files_by_dir[dir_path] = []
            files_by_dir[dir_path].append(os.path.basename(file))

        # Render tree recursively
        return self._render_dir(".", 0, dirs, files_by_dir)

    def _render_dir(
        self,
        dir_path: str,
        depth: int,
        dirs: Set[str],
        files_by_dir: Dict[str, List[str]],
    ) -> str:
        """
        Render a single directory in the tree.

        Args:
            dir_path: Directory path to render.
            depth: Current indentation depth.
            dirs: Set of all directories.
            files_by_dir: Files organized by directory.

        Returns:
            Formatted directory string.
        """
        indent = "  " * depth
        output = ""

        if depth > 0:
            output += f"{indent}{os.path.basename(dir_path)}/\n"

        child_indent = "  " * (depth + 1)

        # Find and render subdirectories first
        children = [
            d for d in dirs
            if os.path.dirname(d) == dir_path and d != dir_path
        ]
        children.sort()

        for child in children:
            output += self._render_dir(child, depth + 1, dirs, files_by_dir)

        # Render files
        files = files_by_dir.get(dir_path, [])
        files.sort()

        for file in files:
            output += f"{child_indent}{file}\n"

        return output

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "path": {
                "type": "string",
                "description": "The absolute path to directory to list (must be absolute, not relative)",
            },
            "ignore": {
                "type": "array",
                "description": "List of glob patterns to ignore",
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
