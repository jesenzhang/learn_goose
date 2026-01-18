"""
Read tool for reading files.

This tool provides file reading with:
- line-based pagination
- image/PDF support as attachments (base64 encoded)
- binary file detection via extension and content analysis
- configurable line and byte limits
- line numbers in output format
- filename suggestions on error
"""

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult, ToolState


DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 50 * 1024

# Common binary file extensions
BINARY_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".bz2", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".lib", ".a",
    ".class", ".jar", ".war", ".ear",
    ".7z", ".rar", ".iso", ".img",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp",
    ".bin", ".dat", ".obj", ".o",
    ".wasm", ".pyc", ".pyo", ".pyd",
    ".pdf",  # Handled separately as attachment
}


class ReadParams(ToolInputSchema):
    """Parameters for the Read tool."""

    filePath: str = Field(..., description="The absolute path to the file to read")
    offset: Optional[int] = Field(
        0,
        description="The line number to start reading from (0-based)",
    )
    limit: Optional[int] = Field(
        DEFAULT_READ_LIMIT,
        description="The number of lines to read (defaults to 2000)",
    )


class ReadTool(Tool):
    """
    Reads files with line-based pagination.

    Features:
    - Line-based pagination with configurable offset and limit
    - Supports images/PDFs as attachments (base64 encoded)
    - Binary file detection via extension and content analysis
    - Line numbers in output format: `00001| content`
    - Suggests similar filenames on error
    - Configurable limits for lines and bytes

    Usage:
    - filePath (required): Absolute path to the file
    - offset (optional): Line number to start from (0-based, default 0)
    - limit (optional): Number of lines to read (default 2000)
    """

    name = "read"
    description = (
        "Reads files with line-based pagination. Supports text files, images, and PDFs. "
        "Images and PDFs are returned as base64-encoded attachments. "
        "Binary files are detected and rejected with an error. "
        "Output includes line numbers in format: '00001| content'. "
        "If the file is larger than the limit, output is truncated with a message "
        "about using the offset parameter to read more."
    )
    input_schema = ReadParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._max_bytes = self.config.get("max_bytes", MAX_BYTES)
        self._max_lines = self.config.get("max_lines", DEFAULT_READ_LIMIT)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Read the file.

        Args:
            params: Dictionary containing 'filePath', optional 'offset', and 'limit'.

        Returns:
            ToolResult with the file content.

        Raises:
            ToolError: If file not found, is binary, or read fails.
        """
        filepath = params["filePath"]
        offset = params.get("offset", 0)
        limit = params.get("limit", self._max_lines)

        # Convert to absolute path if not already
        path = Path(filepath)
        if not path.is_absolute():
            path = Path.cwd() / filepath
            filepath = str(path)

        # Check if file exists
        if not path.exists():
            suggestions = self._get_filename_suggestions(path)
            if suggestions:
                raise ToolError(
                    f"File not found: {filepath}\n\nDid you mean one of these?\n" + "\n".join(suggestions)
                )
            raise ToolError(f"File not found: {filepath}")

        if not path.is_file():
            raise ToolError(f"Not a file: {filepath}")

        # Check if it's an image
        mime_type = mimetypes.guess_type(filepath)[0]
        is_image = mime_type and mime_type.startswith("image/") and mime_type != "image/svg+xml"
        is_pdf = mime_type == "application/pdf"

        if is_image or is_pdf:
            return await self._read_attachment(filepath, mime_type, is_image, is_pdf)

        # Check if it's binary
        if self._is_binary_file(filepath):
            raise ToolError(f"Cannot read binary file: {filepath}")

        # Read text file
        try:
            return await self._read_text_file(filepath, offset, limit)
        except UnicodeDecodeError:
            raise ToolError(f"Cannot read file (encoding error): {filepath}")
        except Exception as e:
            raise ToolError(f"Failed to read file: {e}")

    async def _read_attachment(
        self,
        filepath: str,
        mime_type: Optional[str],
        is_image: bool,
        is_pdf: bool,
    ) -> ToolResult:
        """
        Read image/PDF as base64 attachment.

        Args:
            filepath: Path to the file.
            mime_type: Detected MIME type.
            is_image: Whether this is an image.
            is_pdf: Whether this is a PDF.

        Returns:
            ToolResult with attachment metadata.
        """
        try:
            with open(filepath, "rb") as f:
                file_bytes = f.read()

            base64_data = base64.b64encode(file_bytes).decode("utf-8")
            mime = mime_type or "application/octet-stream"

            return ToolResult(
                content=f"{'Image' if is_image else 'PDF'} read successfully",
                metadata={
                    "preview": f"{'Image' if is_image else 'PDF'} read successfully",
                    "truncated": False,
                    "attachment": {
                        "mime": mime,
                        "size": len(file_bytes),
                        "base64_data": base64_data[:100] + "..." if len(base64_data) > 100 else base64_data,
                    },
                },
            )
        except Exception as e:
            raise ToolError(f"Failed to read {'image' if is_image else 'PDF'}: {e}")

    async def _read_text_file(
        self,
        filepath: str,
        offset: int,
        limit: int,
    ) -> ToolResult:
        """
        Read a text file with pagination.

        Args:
            filepath: Path to the file.
            offset: Starting line number (0-based).
            limit: Maximum lines to read.

        Returns:
            ToolResult with file content.
        """
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            max_line = min(total_lines, offset + limit)

            raw_lines = []
            bytes_read = 0
            truncated_by_bytes = False

            for i in range(offset, max_line):
                line = lines[i].rstrip("\n\r")
                # Truncate long lines
                if len(line) > MAX_LINE_LENGTH:
                    line = line[:MAX_LINE_LENGTH] + "..."

                # Calculate byte size
                line_bytes = len(line.encode("utf-8"))
                if raw_lines:
                    line_bytes += 1  # Newline character

                if bytes_read + line_bytes > self._max_bytes:
                    truncated_by_bytes = True
                    break

                raw_lines.append(line)
                bytes_read += line_bytes

            # Format with line numbers
            formatted_lines = []
            for i, line in enumerate(raw_lines):
                formatted_lines.append(f"{i + offset + 1:05d}| {line}")

            output = "<file>\n" + "\n".join(formatted_lines)

            has_more_lines = total_lines > offset + len(raw_lines)
            truncated = has_more_lines or truncated_by_bytes

            if truncated_by_bytes:
                output += (
                    f"\n\n(Output truncated at {self._max_bytes} bytes. "
                    f"Use 'offset' parameter to read beyond line {offset + len(raw_lines)})"
                )
            elif has_more_lines:
                output += (
                    f"\n\n(File has more lines. "
                    f"Use 'offset' parameter to read beyond line {offset + len(raw_lines)})"
                )
            else:
                output += f"\n\n(End of file - total {total_lines} lines)"

            output += "\n</file>"

            preview = "\n".join(raw_lines[:20])

            return ToolResult(
                content=output,
                metadata={
                    "preview": preview,
                    "truncated": truncated,
                    "total_lines": total_lines,
                    "lines_read": len(raw_lines),
                    "offset": offset,
                },
            )
        except Exception as e:
            raise ToolError(f"Failed to read text file: {e}")

    def _is_binary_file(self, filepath: str) -> bool:
        """
        Check if a file is binary.

        Args:
            filepath: Path to the file.

        Returns:
            True if file appears to be binary.
        """
        path = Path(filepath)
        ext = path.suffix.lower()

        # Check extension first
        if ext in BINARY_EXTENSIONS:
            return True

        # Check file content
        try:
            file_size = path.stat().st_size
            if file_size == 0:
                return False

            buffer_size = min(4096, file_size)
            with open(filepath, "rb") as f:
                buffer = f.read(buffer_size)

            if not buffer:
                return False

            # Count null bytes and non-printable characters
            null_count = buffer.count(0)
            if null_count > 0:
                return True

            non_printable_count = 0
            for byte in buffer:
                if byte < 9 or (13 < byte < 32):
                    non_printable_count += 1

            # If >30% non-printable, consider it binary
            return non_printable_count / len(buffer) > 0.3

        except Exception:
            # On error, assume text
            return False

    def _get_filename_suggestions(self, path: Path) -> List[str]:
        """
        Get filename suggestions for a file that doesn't exist.

        Args:
            path: The path that doesn't exist.

        Returns:
            List of suggested file paths.
        """
        base = path.name.lower()
        dir_path = path.parent

        if not dir_path.exists():
            return []

        try:
            entries = os.listdir(dir_path)
        except Exception:
            return []

        suggestions = []
        for entry in entries:
            entry_lower = entry.lower()
            if base in entry_lower or entry_lower in base:
                suggestions.append(str(dir_path / entry))

        return sorted(suggestions)[:3]

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to read",
            },
            "offset": {
                "type": "integer",
                "description": "The line number to start reading from (0-based)",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "The number of lines to read (defaults to 2000)",
                "default": DEFAULT_READ_LIMIT,
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
