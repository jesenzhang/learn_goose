"""
Edit tool for intelligent file editing.

This tool provides intelligent file editing with multiple fuzzy matching strategies:
- SimpleReplacer - Exact match
- LineTrimmedReplacer - Trimmed line match
- WhitespaceNormalizedReplacer - Whitespace-insensitive match
- IndentationFlexibleReplacer - Indentation-insensitive match
- EscapeNormalizedReplacer - Escaped sequence handling
- TrimmedBoundaryReplacer - Trimmed boundary matching
- Levenshtein distance for similarity matching
- File locking for concurrent access
- Diff generation
"""

import difflib
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


# Similarity thresholds
SINGLE_CANDIDATE_SIMILARITY_THRESHOLD = 0.0
MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD = 0.3


class EditParams(ToolInputSchema):
    """Parameters for the Edit tool."""

    filePath: str = Field(..., description="The absolute path to the file to modify")
    oldString: str = Field(..., description="The text to replace")
    newString: str = Field(..., description="The text to replace it with (must be different from oldString)")
    replaceAll: Optional[bool] = Field(False, description="Replace all occurrences of oldString (default false)")


def levenshtein(a: str, b: str) -> int:
    """
    Calculate the Levenshtein distance between two strings.

    Args:
        a: First string.
        b: Second string.

    Returns:
        The edit distance.
    """
    # Handle empty strings
    if a == "" or b == "":
        return max(len(a), len(b))

    # Initialize matrix
    matrix = [[0 for _ in range(len(b) + 1)] for _ in range(len(a) + 1)]

    for i in range(len(a) + 1):
        matrix[i][0] = i

    for j in range(len(b) + 1):
        matrix[0][j] = j

    # Fill matrix
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )

    return matrix[len(a)][len(b)]


class EditTool(BaseTool):
    """
    Intelligent file editing with multiple fuzzy matching strategies.

    Features:
    - Multiple replacer strategies for fuzzy matching
    - Levenshtein distance for similarity matching
    - File locking for concurrent access
    - Diff generation for permission requests

    Usage:
    - filePath (required): Absolute path to the file
    - oldString (required): Text to replace
    - newString (required): Replacement text
    - replaceAll (optional): Replace all occurrences (default false)
    """

    name = "edit"
    description = (
        "Intelligent file editing with multiple fuzzy matching strategies. "
        "Supports exact match, trimmed lines, whitespace-insensitive, "
        "indentation-flexible, escape-normalized, and context-aware matching. "
        "Generates diffs for permission requests. "
        "Use replaceAll=True to replace all occurrences."
    )
    input_schema = EditParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._lock_enabled = self.config.get("lock_enabled", True)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the edit.

        Args:
            params: Dictionary containing 'filePath', 'oldString', 'newString', and optional 'replaceAll'.

        Returns:
            ToolResult with edit confirmation.

        Raises:
            ToolError: If file not found, oldString equals newString, or no unique match found.
        """
        file_path = params["filePath"]
        old_string = params["oldString"]
        new_string = params["newString"]
        replace_all = params.get("replaceAll", False)

        # Convert to absolute path
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / file_path
            file_path = str(path)

        if old_string == new_string:
            raise ToolError("oldString and newString must be different")

        # Check if file exists
        if not path.exists():
            raise ToolError(f"File not found: {file_path}")

        if not path.is_file():
            raise ToolError(f"Not a file: {file_path}")

        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise ToolError(f"Failed to read file: {e}")

        # Perform replacement
        try:
            new_content = self._replace(content, old_string, new_string, replace_all)
        except ValueError as e:
            raise ToolError(str(e))

        # Generate diff
        diff = self._generate_diff(content, new_content, file_path)

        # Calculate additions/deletions
        additions = 0
        deletions = 0
        for line in difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=file_path,
            tofile=file_path,
        ):
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        # Write new content
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            raise ToolError(f"Failed to write file: {e}")

        return ToolResult(
            content="Edit applied successfully.",
            metadata={
                "diff": diff,
                "additions": additions,
                "deletions": deletions,
                "file": file_path,
            },
        )

    def _replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool,
    ) -> str:
        """
        Perform replacement with fuzzy matching strategies.

        Args:
            content: Original file content.
            old_string: String to replace.
            new_string: Replacement string.
            replace_all: Whether to replace all occurrences.

        Returns:
            Modified content.

        Raises:
            ValueError: If oldString not found or multiple matches found.
        """
        # Try all replacers in order
        for replacer in [
            self._simple_replacer,
            self._line_trimmed_replacer,
            self._whitespace_normalized_replacer,
            self._indentation_flexible_replacer,
            self._escape_normalized_replacer,
            self._trimmed_boundary_replacer,
        ]:
            for match in replacer(content, old_string):
                index = content.find(match)
                if index == -1:
                    continue

                if replace_all:
                    return content.replace(match, new_string)

                # Check for unique match
                last_index = content.rfind(match)
                if index != last_index:
                    continue

                return content[:index] + new_string + content[index + len(match):]

        # Try multi-occurrence replacer last
        for match in self._multi_occurrence_replacer(content, old_string):
            if replace_all:
                return content.replace(match, new_string)

            index = content.find(match)
            last_index = content.rfind(match)

            if index == -1:
                continue

            if index == last_index:
                return content[:index] + new_string + content[index + len(match):]

        raise ValueError(
            "oldString not found in content. "
            "Provide more surrounding lines in oldString to identify the correct match."
        )

    def _simple_replacer(self, content: str, find: str) -> Generator[str, None, None]:
        """Exact match replacer."""
        yield find

    def _line_trimmed_replacer(self, content: str, find: str) -> Generator[str, None, None]:
        """Trimmed line match replacer."""
        original_lines = content.split("\n")
        search_lines = find.split("\n")

        # Remove trailing empty line
        if search_lines and search_lines[-1] == "":
            search_lines.pop()

        for i in range(len(original_lines) - len(search_lines) + 1):
            matches = True

            for j in range(len(search_lines)):
                original_trimmed = original_lines[i + j].strip()
                search_trimmed = search_lines[j].strip()

                if original_trimmed != search_trimmed:
                    matches = False
                    break

            if matches:
                match_start = 0
                for k in range(i):
                    match_start += len(original_lines[k]) + 1

                match_end = match_start
                for k in range(i, i + len(search_lines)):
                    match_end += len(original_lines[k])
                    if k < i + len(search_lines) - 1:
                        match_end += 1

                yield content[match_start:match_end]

    def _whitespace_normalized_replacer(
        self,
        content: str,
        find: str,
    ) -> Generator[str, None, None]:
        """Whitespace-insensitive match replacer."""
        def normalize_whitespace(text: str) -> str:
            return " ".join(text.split()).strip()

        normalized_find = normalize_whitespace(find)

        # Check line matches
        for line in content.split("\n"):
            if normalize_whitespace(line) == normalized_find:
                yield line

        # Check substring matches
        for line in content.split("\n"):
            normalized_line = normalize_whitespace(line)
            if normalized_find in normalized_line:
                # Find actual match
                words = find.strip().split()
                if words:
                    pattern = r"\s+".join(re.escape(word) for word in words)
                    import re
                    match = re.search(pattern, line)
                    if match:
                        yield match.group(0)

        # Check multi-line matches
        find_lines = find.split("\n")
        if len(find_lines) > 1:
            for i in range(len(content.split("\n")) - len(find_lines) + 1):
                block = "\n".join(content.split("\n")[i:i + len(find_lines)])
                if normalize_whitespace(block) == normalized_find:
                    yield block

    def _indentation_flexible_replacer(
        self,
        content: str,
        find: str,
    ) -> Generator[str, None, None]:
        """Indentation-insensitive match replacer."""
        def remove_indentation(text: str) -> str:
            lines = text.split("\n")
            non_empty = [l for l in lines if l.strip()]

            if not non_empty:
                return text

            min_indent = min(
                len(l) - len(l.lstrip()) for l in non_empty
            )

            return "\n".join(
                l if l.strip() == "" else l[min_indent:] for l in lines
            )

        normalized_find = remove_indentation(find)
        content_lines = content.split("\n")
        find_lines = find.split("\n")

        for i in range(len(content_lines) - len(find_lines) + 1):
            block = "\n".join(content_lines[i:i + len(find_lines)])
            if remove_indentation(block) == normalized_find:
                yield block

    def _escape_normalized_replacer(
        self,
        content: str,
        find: str,
    ) -> Generator[str, None, None]:
        """Escape sequence normalized replacer."""
        def unescape_string(s: str) -> str:
            replacements = {
                "\\n": "\n",
                "\\t": "\t",
                "\\r": "\r",
                "\\'": "'",
                '\\"': '"',
                "\\`": "`",
                "\\\\": "\\",
            }
            for escaped, unescaped in replacements.items():
                s = s.replace(escaped, unescaped)
            return s

        unescaped_find = unescape_string(find)

        # Try direct match
        if unescaped_find in content:
            yield unescaped_find

        # Also try matching against escaped content
        lines = content.split("\n")
        find_lines = unescaped_find.split("\n")

        for i in range(len(lines) - len(find_lines) + 1):
            block = "\n".join(lines[i:i + len(find_lines)])
            if unescape_string(block) == unescaped_find:
                yield block

    def _trimmed_boundary_replacer(
        self,
        content: str,
        find: str,
    ) -> Generator[str, None, None]:
        """Trimmed boundary match replacer."""
        trimmed_find = find.strip()

        if trimmed_find == find:
            return  # Already trimmed

        if trimmed_find in content:
            yield trimmed_find

        # Check blocks
        lines = content.split("\n")
        find_lines = find.split("\n")

        for i in range(len(lines) - len(find_lines) + 1):
            block = "\n".join(lines[i:i + len(find_lines)])
            if block.strip() == trimmed_find:
                yield block

    def _multi_occurrence_replacer(
        self,
        content: str,
        find: str,
    ) -> Generator[str, None, None]:
        """Yield all occurrences for replaceAll support."""
        start_index = 0

        while True:
            index = content.find(find, start_index)
            if index == -1:
                break

            yield find
            start_index = index + len(find)

    def _generate_diff(self, old: str, new: str, file_path: str) -> str:
        """
        Generate unified diff between old and new content.

        Args:
            old: Original content.
            new: New content.
            file_path: File path for diff header.

        Returns:
            Unified diff string.
        """
        diff_lines = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=file_path,
            tofile=file_path,
            lineterm="",
        )

        return "\n".join(diff_lines)

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to modify",
            },
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
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
