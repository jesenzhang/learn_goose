"""
Builtin MCP Tools - Ported from goose-rs.

This module contains all builtin MCP tools compatible with
goose-rs tool architecture.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..mcp.adapter import MCPTool, register_builtin, ErrorData, ErrorCode

logger = logging.getLogger(__name__)


# ============================================================================
# Developer Tools
# ============================================================================

class ShellParams(BaseModel):
    """Parameters for shell tool."""
    command: str = Field(..., description="The command string to execute in shell")


@register_builtin("shell", "Execute shell commands")
class ShellTool(MCPTool):
    """
    Execute shell commands.

    Equivalent to goose-rs' computercontroller::shell tool.
    """

    name = "shell"
    description = "Execute a shell command and return the output"
    input_schema = ShellParams

    async def execute(self, params: ShellParams) -> str:
        """
        Execute shell command.

        Args:
            params: Shell parameters

        Returns:
            Command output as string
        """
        try:
            process = await asyncio.create_subprocess_shell(
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(params.command),
                timeout=30.0
            )

            result = stdout or ""
            if stderr:
                result += f"\n[STDERR]: {stderr}"

            return result.strip()

        except asyncio.TimeoutError:
            raise Exception("Command timed out after 30 seconds")
        except Exception as e:
            raise Exception(f"Failed to execute command: {str(e)}")


class WebScrapeParams(BaseModel):
    """Parameters for web_scrape tool."""
    url: str = Field(..., description="The URL to fetch content from")
    save_as: str = Field(default="text", description="Format of response: 'text', 'json', or 'binary'")


@register_builtin("web_scrape", "Fetch web page content")
class WebScrapeTool(MCPTool):
    """
    Fetch and scrape web page content.

    Equivalent to goose-rs' computercontroller::web_scrape tool.
    """

    name = "web_scrape"
    description = "Fetch and return content from a URL"
    input_schema = WebScrapeParams

    async def execute(self, params: WebScrapeParams) -> Union[str, Dict[str, Any]]:
        """
        Fetch web content.

        Args:
            params: Web scraping parameters

        Returns:
            Content as string or JSON
        """
        try:
            import aiohttp
            import base64

            async with aiohttp.ClientSession() as session:
                async with session.get(params.url) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}: {response.reason}")

                    content_bytes = await response.read()

                    if params.save_as == "binary":
                        content_b64 = base64.b64encode(content_bytes).decode("utf-8")
                        return {
                            "url": params.url,
                            "data": content_b64,
                            "size": len(content_bytes),
                            "mime_type": response.headers.get("Content-Type", "application/octet-stream")
                        }
                    elif params.save_as == "json":
                        content_text = content_bytes.decode("utf-8", errors="ignore")
                        try:
                            return json.loads(content_text)
                        except json.JSONDecodeError:
                            return {"raw_text": content_text}
                    else:
                        return content_bytes.decode("utf-8", errors="ignore")

        except ImportError:
            raise Exception("aiohttp library required for web_scrape tool")
        except Exception as e:
            raise Exception(f"Failed to scrape URL: {str(e)}")


# ============================================================================
# File System Tools
# ============================================================================

class ReadFileParams(BaseModel):
    """Parameters for read_file tool."""
    path: str = Field(..., description="Absolute or relative path to file")
    view_range: Optional[List[int]] = Field(None, description="Optional [start, end] line numbers (1-indexed)")


@register_builtin("read_file", "Read file contents")
class ReadFileTool(MCPTool):
    """
    Read file contents.

    Equivalent to goose-rs' developer::text_editor (view command).
    """

    name = "read_file"
    description = "Read and return the contents of a file"
    input_schema = ReadFileParams

    async def execute(self, params: ReadFileParams) -> str:
        """
        Read file content.

        Args:
            params: File reading parameters

        Returns:
            File content as string
        """
        try:
            file_path = Path(params.path)

            if not file_path.exists():
                raise Exception(f"File not found: {params.path}")

            content = file_path.read_text(encoding="utf-8", errors="ignore")

            # Apply view range if specified
            if params.view_range and len(params.view_range) == 2:
                start_line = params.view_range[0] - 1  # Convert to 0-indexed
                end_line = params.view_range[1] if params.view_range[1] != -1 else None

                lines = content.split("\n")
                if end_line is not None:
                    lines = lines[start_line:end_line]
                else:
                    lines = lines[start_line:]

                # Add line numbers
                numbered_lines = [
                    f"{i + start_line + 1}: {line}"
                    for i, line in enumerate(lines)
                ]
                content = "\n".join(numbered_lines)

            return content

        except Exception as e:
            raise Exception(f"Failed to read file: {str(e)}")


class WriteFileParams(BaseModel):
    """Parameters for write_file tool."""
    path: str = Field(..., description="Absolute or relative path to file")
    content: str = Field(..., description="Content to write to file")
    create_dirs: bool = Field(default=False, description="Create parent directories if needed")


@register_builtin("write_file", "Write to file")
class WriteFileTool(MCPTool):
    """
    Write content to file.

    Equivalent to goose-rs' developer::text_editor (write command).
    """

    name = "write_file"
    description = "Write content to a file (creates or overwrites)"
    input_schema = WriteFileParams

    async def execute(self, params: WriteFileParams) -> str:
        """
        Write file content.

        Args:
            params: File writing parameters

        Returns:
            Success message
        """
        try:
            file_path = Path(params.path)

            if params.create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(params.content, encoding="utf-8")

            return f"Successfully wrote {len(params.content)} bytes to {params.path}"

        except Exception as e:
            raise Exception(f"Failed to write file: {str(e)}")


# ============================================================================
# Memory Tools
# ============================================================================

class RememberMemoryParams(BaseModel):
    """Parameters for remember_memory tool."""
    category: str = Field(..., description="The category to store memory in")
    data: str = Field(..., description="The data to remember")
    tags: List[str] = Field(default_factory=list, description="Optional tags for memory")
    is_global: bool = Field(default=False, description="Store globally or locally")


@register_builtin("remember_memory", "Store information in memory")
class RememberMemoryTool(MCPTool):
    """
    Store information in categorized memory.

    Equivalent to goose-rs' memory::remember_memory tool.
    """

    name = "remember_memory"
    description = "Store information in a category with optional tags"
    input_schema = RememberMemoryParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.memory_dir = Path(config.get("memory_dir", ".goose/memory")) if config else Path(".goose/memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, params: RememberMemoryParams) -> str:
        """
        Store memory.

        Args:
            params: Memory parameters

        Returns:
            Success message
        """
        try:
            # Determine storage path
            if params.is_global:
                # Global storage: ~/.config/goose/memory/
                config_dir = Path.home() / ".config" / "goose" / "memory"
            else:
                # Local storage: .goose/memory
                config_dir = self.memory_dir

            category_dir = config_dir / params.category
            category_dir.mkdir(parents=True, exist_ok=True)

            # Save memory with timestamp
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            memory_file = category_dir / f"{timestamp}.json"

            memory_data = {
                "data": params.data,
                "tags": params.tags,
                "timestamp": time.time()
            }

            memory_file.write_text(json.dumps(memory_data, indent=2), encoding="utf-8")

            return f"Stored memory in category '{params.category}' with tags: {', '.join(params.tags) if params.tags else 'none'}"

        except Exception as e:
            raise Exception(f"Failed to store memory: {str(e)}")


class RetrieveMemoriesParams(BaseModel):
    """Parameters for retrieve_memories tool."""
    category: str = Field(default="*", description="Category to retrieve from ('*' for all)")
    is_global: bool = Field(default=False, description="Retrieve from global or local storage")


@register_builtin("retrieve_memories", "Retrieve stored memories")
class RetrieveMemoriesTool(MCPTool):
    """
    Retrieve stored memories.

    Equivalent to goose-rs' memory::retrieve_memories tool.
    """

    name = "retrieve_memories"
    description = "Retrieve memories from a category or all memories"
    input_schema = RetrieveMemoriesParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.memory_dir = Path(config.get("memory_dir", ".goose/memory")) if config else Path(".goose/memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, params: RetrieveMemoriesParams) -> Union[str, List[Dict[str, Any]]]:
        """
        Retrieve memories.

        Args:
            params: Retrieval parameters

        Returns:
            List of memory entries or message
        """
        try:
            if params.is_global:
                config_dir = Path.home() / ".config" / "goose" / "memory"
            else:
                config_dir = self.memory_dir

            if params.category == "*":
                # Get all memories
                memories = []
                for category_dir in config_dir.iterdir():
                    if category_dir.is_dir():
                        for memory_file in category_dir.glob("*.json"):
                            with open(memory_file, "r", encoding="utf-8") as f:
                                memories.append(json.load(f))
                return memories
            else:
                category_dir = config_dir / params.category
                if not category_dir.exists():
                    return f"No memories found in category '{params.category}'"

                memories = []
                for memory_file in category_dir.glob("*.json"):
                    with open(memory_file, "r", encoding="utf-8") as f:
                        memories.append(json.load(f))
                return memories

        except Exception as e:
            raise Exception(f"Failed to retrieve memories: {str(e)}")


# ============================================================================
# Directory Tools
# ============================================================================

class ListDirectoryParams(BaseModel):
    """Parameters for list_directory tool."""
    path: str = Field(default=".", description="Path to list (default: current directory)")


@register_builtin("list_directory", "List directory contents")
class ListDirectoryTool(MCPTool):
    """
    List directory contents.

    Equivalent to goose-rs' shell commands for directory listing.
    """

    name = "list_directory"
    description = "List files and directories in a path"
    input_schema = ListDirectoryParams

    async def execute(self, params: ListDirectoryParams) -> Dict[str, Any]:
        """
        List directory.

        Args:
            params: Directory parameters

        Returns:
            Dictionary with files and directories
        """
        try:
            dir_path = Path(params.path)

            if not dir_path.exists():
                raise Exception(f"Path not found: {params.path}")

            files = []
            directories = []

            for item in dir_path.iterdir():
                if item.is_dir():
                    directories.append(item.name)
                else:
                    files.append({
                        "name": item.name,
                        "size": item.stat().st_size
                    })

            return {
                "path": str(dir_path.resolve()),
                "directories": sorted(directories),
                "files": sorted(files, key=lambda x: x["name"])
            }

        except Exception as e:
            raise Exception(f"Failed to list directory: {str(e)}")


# ============================================================================
# Search Tools
# ============================================================================

class SearchFilesParams(BaseModel):
    """Parameters for search_files tool."""
    pattern: str = Field(..., description="Search pattern (filename or content)")
    path: str = Field(default=".", description="Path to search in")
    search_content: bool = Field(default=False, description="Search file contents instead of filenames")


@register_builtin("search_files", "Search files")
class SearchFilesTool(MCPTool):
    """
    Search for files by name or content.

    Similar to goose-rs' ripgrep integration.
    """

    name = "search_files"
    description = "Search for files by pattern in filename or content"
    input_schema = SearchFilesParams

    async def execute(self, params: SearchFilesParams) -> List[Dict[str, Any]]:
        """
        Search files.

        Args:
            params: Search parameters

        Returns:
            List of matching files with context
        """
        try:
            dir_path = Path(params.path)
            results = []

            for file_path in dir_path.rglob("*"):
                if not file_path.is_file():
                    continue

                if params.search_content:
                    # Search in file content
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        lines = content.split("\n")
                        for i, line in enumerate(lines, 1):
                            if params.pattern.lower() in line.lower():
                                results.append({
                                    "path": str(file_path),
                                    "line": i,
                                    "content": line.strip(),
                                    "match": params.pattern
                                })
                    except Exception:
                        continue
                else:
                    # Search by filename
                    if params.pattern.lower() in file_path.name.lower():
                        results.append({
                            "path": str(file_path),
                            "type": "file"
                        })

            return results

        except Exception as e:
            raise Exception(f"Failed to search files: {str(e)}")


# ============================================================================
# Initialize all tools
# ============================================================================

def get_builtin_tools_info() -> List[Dict[str, Any]]:
    """
    Get information about all builtin tools.

    Returns:
        List of tool definitions with schemas
    """
    from ..mcp.adapter import get_builtin_registry, list_builtin_tools

    registry = get_builtin_registry()
    tools = []

    for definition in list_builtin_tools():
        # Create a temporary instance to get schema
        try:
            tool = definition.tool_class()
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "schema": tool.schema
            })
        except Exception as e:
            logger.error(f"Failed to load tool {definition.name}: {e}")

    return tools


def get_tool_instance(name: str, config: Optional[Dict[str, Any]] = None) -> Optional[MCPTool]:
    """
    Get a tool instance by name.

    Args:
        name: Tool name
        config: Optional configuration

    Returns:
        Tool instance or None
    """
    from ..mcp.adapter import get_builtin_tool
    return get_builtin_tool(name, config)


def list_tool_names() -> List[str]:
    """
    List all registered tool names.

    Returns:
        List of tool names
    """
    from ..mcp.adapter import list_builtin_tools
    return [t.name for t in list_builtin_tools()]
