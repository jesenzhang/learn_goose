"""
Builtin Tools

内置工具实现，集成到 goose-system 工具系统中。

使用方式:
    from goose.tools import ToolExecutor, FunctionTool
    from goose.tools.builtin import create_builtin_tools, register_builtin_tools

    executor = ToolExecutor()
    register_builtin_tools(executor)

    # 执行工具
    result = await executor.execute_by_name("read", {"filePath": "/path/to/file"})
"""

import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any, List, Optional

from .base import Tool, FunctionTool


def read_file(filePath: str, offset: int = 0, limit: int = 2000) -> Dict[str, Any]:
    """
    Read a file with line-based pagination.
    
    Args:
        filePath: Absolute path to the file
        offset: Line number to start from (0-based)
        limit: Number of lines to read
    
    Returns:
        Dict with content and metadata
    """
    path = Path(filePath)
    
    if not path.exists():
        return {"error": f"File not found: {filePath}"}
    
    if not path.is_file():
        return {"error": f"Not a file: {filePath}"}
    
    try:
        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        max_line = min(total_lines, offset + limit)
        
        raw_lines = []
        for i in range(offset, max_line):
            line = lines[i].rstrip("\n\r")
            raw_lines.append(f"{i + offset + 1:05d}| {line}")
        
        output = "<file>\n" + "\n".join(raw_lines)
        
        has_more = total_lines > offset + len(raw_lines)
        if has_more:
            output += f"\n\n(File has {total_lines} total lines)"
        
        output += "\n</file>"
        
        return {
            "content": output,
            "preview": "\n".join(raw_lines[:20]),
            "truncated": has_more,
            "total_lines": total_lines,
            "lines_read": len(raw_lines),
        }
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}


def write_file(filePath: str, content: str) -> Dict[str, Any]:
    """
    Write content to a file.
    
    Args:
        filePath: Absolute path to the file
        content: Content to write
    
    Returns:
        Dict with result info
    """
    path = Path(filePath)
    
    if not path.is_absolute():
        return {"error": "filePath must be absolute"}
    
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filePath, "w", encoding="utf-8") as f:
            f.write(content)
        
        line_count = len(content.splitlines())
        char_count = len(content)
        
        return {
            "content": f"Wrote {line_count} lines, {char_count} characters to {filePath}",
            "lines": line_count,
            "characters": char_count,
        }
    except Exception as e:
        return {"error": f"Failed to write file: {e}"}


def edit_file(filePath: str, oldString: str, newString: str) -> Dict[str, Any]:
    """
    Edit a file by replacing exact string.
    
    Args:
        filePath: Absolute path to the file
        oldString: Text to replace
        newString: Replacement text
    
    Returns:
        Dict with result info
    """
    path = Path(filePath)
    
    if not path.exists():
        return {"error": f"File not found: {filePath}"}
    
    try:
        with open(filePath, "r", encoding="utf-8") as f:
            content = f.read()
        
        if oldString not in content:
            return {"error": "String not found in file"}
        
        new_content = content.replace(oldString, newString, 1)
        
        with open(filePath, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return {
            "content": f"Edited {filePath}",
            "filePath": filePath,
        }
    except Exception as e:
        return {"error": f"Failed to edit file: {e}"}


def glob_files(pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
    """
    Find files matching a glob pattern.
    
    Args:
        pattern: Glob pattern (e.g., "**/*.py")
        path: Directory to search (defaults to current directory)
    
    Returns:
        Dict with list of matching files
    """
    search_path = Path(path) if path else Path.cwd()
    
    if not search_path.exists():
        return {"error": f"Directory not found: {search_path}"}
    
    if not search_path.is_dir():
        return {"error": f"Not a directory: {search_path}"}
    
    try:
        matches = list(search_path.glob(pattern))
        matches.sort(key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
        
        file_paths = [str(m) for m in matches if m.is_file()]
        
        return {
            "content": f"Found {len(file_paths)} files:\n" + "\n".join(f"  {p}" for p in file_paths),
            "files": file_paths,
            "count": len(file_paths),
        }
    except Exception as e:
        return {"error": f"Glob failed: {e}"}


def grep_files(
    pattern: str,
    path: Optional[str] = None,
    include: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for regex pattern in files.
    
    Args:
        pattern: Regex pattern to search for
        path: Directory to search (defaults to current directory)
        include: File pattern to include (e.g., "*.py")
    
    Returns:
        Dict with matching lines
    """
    search_path = Path(path) if path else Path.cwd()
    
    if not search_path.exists():
        return {"error": f"Directory not found: {search_path}"}
    
    if not search_path.is_dir():
        return {"error": f"Not a directory: {search_path}"}
    
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"error": f"Invalid regex pattern: {e}"}
    
    matches = []
    
    for root, _, filenames in os.walk(search_path):
        for filename in filenames:
            if include:
                if include.startswith("*.{") and include.endswith("}"):
                    exts = include[3:-1].split(",")
                    base = filename.rsplit(".", 1)
                    if len(base) == 2:
                        if f".{base[1]}" not in exts:
                            continue
                    elif not filename.endswith(include[1:-1]):
                        continue
                elif not filename.endswith(include[1:]):
                    continue
            
            file_path = Path(root) / filename
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            matches.append({
                                "file": str(file_path),
                                "line": line_num,
                                "text": line.rstrip("\n\r")[:2000],
                            })
            except (OSError, UnicodeDecodeError):
                continue
    
    if not matches:
        return {"content": "No matches found", "matches": []}
    
    matches.sort(key=lambda x: x["line"], reverse=True)
    matches = matches[:100]
    
    output_lines = [f"Found {len(matches)} matches"]
    current_file = ""
    
    for match in matches:
        if match["file"] != current_file:
            if current_file:
                output_lines.append("")
            current_file = match["file"]
            output_lines.append(f"{match['file']}:")
        
        output_lines.append(f"  Line {match['line']}: {match['text']}")
    
    return {
        "content": "\n".join(output_lines),
        "matches": matches,
        "count": len(matches),
    }


def list_dir(path: Optional[str] = None) -> Dict[str, Any]:
    """
    List directory contents.
    
    Args:
        path: Directory path (defaults to current directory)
    
    Returns:
        Dict with directory contents
    """
    search_path = Path(path) if path else Path.cwd()
    
    if not search_path.exists():
        return {"error": f"Path not found: {search_path}"}
    
    if not search_path.is_dir():
        return {"error": f"Not a directory: {search_path}"}
    
    try:
        entries = list(search_path.iterdir())
        entries.sort(key=lambda x: (not x.is_file(), x.name.lower()))
        
        lines = [f"Contents of {search_path}:"]
        
        for entry in entries:
            if entry.is_dir():
                lines.append(f"  [DIR]  {entry.name}/")
            else:
                try:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    lines.append(f"  [FILE] {entry.name} ({size_str})")
                except OSError:
                    lines.append(f"  [FILE] {entry.name}")
        
        return {"content": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Failed to list directory: {e}"}


def run_bash(command: str, timeout: Optional[int] = None, workdir: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a bash command.
    
    Args:
        command: Command to execute
        timeout: Timeout in milliseconds
        workdir: Working directory
    
    Returns:
        Dict with command output
    """
    import sys
    
    timeout_seconds = timeout / 1000 if timeout else None
    work_dir = workdir or str(Path.cwd())
    
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(
                ["cmd.exe", "/c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=work_dir,
                text=True,
            )
        else:
            proc = subprocess.Popen(
                ["bash", "-c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=work_dir,
                text=True,
            )
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            
            output = stdout
            if stderr:
                output += stderr
            
            if proc.returncode != 0:
                return {
                    "content": output,
                    "error": f"Command failed with exit code {proc.returncode}",
                    "exit_code": proc.returncode,
                }
            
            return {
                "content": output,
                "exit_code": 0,
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {
                "content": "",
                "error": "Command timed out",
                "exit_code": -1,
            }
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


def create_builtin_tools() -> List[FunctionTool]:
    """
    Create all builtin tools as FunctionTool instances.
    
    Returns:
        List of FunctionTool instances
    """
    return [
        FunctionTool(
            name="read",
            description="Read a file with line-based pagination. Supports text files with line numbers.",
            function=read_file,
            parameters={
                "type": "object",
                "properties": {
                    "filePath": {"type": "string", "description": "The absolute path to the file to read"},
                    "offset": {"type": "integer", "description": "Line number to start from (0-based)", "default": 0},
                    "limit": {"type": "integer", "description": "Number of lines to read", "default": 2000},
                },
                "required": ["filePath"],
            },
        ),
        FunctionTool(
            name="write",
            description="Write content to a file. Creates parent directories if needed.",
            function=write_file,
            parameters={
                "type": "object",
                "properties": {
                    "filePath": {"type": "string", "description": "The absolute path to the file to write"},
                    "content": {"type": "string", "description": "The content to write to the file"},
                },
                "required": ["filePath", "content"],
            },
        ),
        FunctionTool(
            name="edit",
            description="Edit a file by replacing exact string matches.",
            function=edit_file,
            parameters={
                "type": "object",
                "properties": {
                    "filePath": {"type": "string", "description": "The absolute path to the file to edit"},
                    "oldString": {"type": "string", "description": "The text to replace"},
                    "newString": {"type": "string", "description": "The replacement text"},
                },
                "required": ["filePath", "oldString", "newString"],
            },
        ),
        FunctionTool(
            name="glob",
            description="Find files matching a glob pattern. Supports recursive patterns like '**/*.py'.",
            function=glob_files,
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "The glob pattern to match"},
                    "path": {"type": "string", "description": "The directory to search in", "default": "."},
                },
                "required": ["pattern"],
            },
        ),
        FunctionTool(
            name="grep",
            description="Search for regex patterns in file contents.",
            function=grep_files,
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "The regex pattern to search for"},
                    "path": {"type": "string", "description": "The directory to search in", "default": "."},
                    "include": {"type": "string", "description": "File pattern to include (e.g., '*.py')"},
                },
                "required": ["pattern"],
            },
        ),
        FunctionTool(
            name="ls",
            description="List files and directories in a path.",
            function=list_dir,
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The directory to list", "default": "."},
                },
            },
        ),
        FunctionTool(
            name="bash",
            description="Execute a bash command. Returns stdout and stderr.",
            function=run_bash,
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in milliseconds"},
                    "workdir": {"type": "string", "description": "Working directory"},
                },
                "required": ["command"],
            },
        ),
    ]


def register_builtin_tools(executor: "ToolExecutor") -> None:
    """
    Register all builtin tools with a ToolExecutor.
    
    Args:
        executor: ToolExecutor instance to register with
    """
    executor.register_handler("read", read_file)
    executor.register_handler("write", write_file)
    executor.register_handler("edit", edit_file)
    executor.register_handler("glob", glob_files)
    executor.register_handler("grep", grep_files)
    executor.register_handler("ls", list_dir)
    executor.register_handler("bash", run_bash)
