"""
Developer Platform Extension

Provides developer tools including:
- text_editor: View, write, edit files
- shell: Execute shell commands
- analyze: Analyze code structure
- list_windows: List available windows
- screen_capture: Capture screenshots
- image_processor: Process images

Reference: goose-rs/crates/goose-mcp/src/developer/rmcp_developer.rs
"""

import base64
import os
import platform as sys_platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...session import SessionManager


class DeveloperPlatformExtension:
    """Developer Platform Extension providing development tools"""

    EXTENSION_NAME = "developer"

    def __init__(self, session_manager: Optional[SessionManager] = None):
        self.session_manager = session_manager
        self.file_history: Dict[str, List[str]] = {}
        self._initialized = False
        self._os = sys_platform.system()

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the developer extension"""
        cwd = Path.cwd().resolve()
        shell_info = os.environ.get("SHELL", "/bin/sh")
        in_container = self._check_container()

        os_instructions = self._get_os_instructions(cwd, shell_info, in_container)

        self._initialized = True

        return {
            "name": self.EXTENSION_NAME,
            "version": "1.0.0",
            "description": "Developer tools for code editing and shell commands",
            "instructions": os_instructions,
        }

    def _check_container(self) -> bool:
        """Check if running in a container"""
        return os.path.exists("/.dockerenv") or os.environ.get("container", "") == "podman"

    def _get_os_instructions(self, cwd: Path, shell_info: str, in_container: bool) -> str:
        """Get OS-specific instructions"""
        container_info = "container: true" if in_container else ""

        if self._os == "Windows":
            return f"""The developer extension gives you the capabilities to edit code files and run shell commands,
and can be used to solve a wide range of problems.

You can use the shell tool to run Windows commands (PowerShell or CMD).
When using paths, you can use either backslashes or forward slashes.

Use the shell tool as needed to locate files or interact with the project.

Your windows/screen tools can be used for visual debugging. You should not use these tools unless
prompted to, but you can mention they are available if they are relevant.

operating system: {self._os}
current directory: {cwd}
{container_info}"""
        else:
            return f"""The developer extension gives you the capabilities to edit code files and run shell commands,
and can be used to solve a wide range of problems.

You can use the shell tool to run any command that would work on the relevant operating system.
Use the shell tool as needed to locate files or interact with the project.

Your windows/screen tools can be used for visual debugging. You should not use these tools unless
prompted to, but you can mention they are available if they are relevant.

Always prefer ripgrep (rg -C 3) to grep.

operating system: {self._os}
current directory: {cwd}
shell: {shell_info}
{container_info}"""

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        if not self._initialized:
            await self.initialize()

        return [
            {
                "name": "text_editor",
                "description": "Perform text editing operations on files. Commands: view, write, str_replace, insert, undo_edit.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to file or directory"},
                        "command": {"type": "string", "description": "Operation: view, write, str_replace, insert, undo_edit"},
                        "file_text": {"type": "string", "description": "Content for write command"},
                        "old_str": {"type": "string", "description": "Text to replace for str_replace"},
                        "new_str": {"type": "string", "description": "New text for str_replace"},
                        "insert_line": {"type": "integer", "description": "Line number for insert command"},
                        "view_range": {"type": "array", "description": "Start and end line numbers to view"},
                    },
                    "required": ["path", "command"],
                }
            },
            {
                "name": "shell",
                "description": "Execute a command in the shell. Returns output and error.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"},
                    },
                    "required": ["command"],
                }
            },
            {
                "name": "analyze",
                "description": "Analyze code structure. Directory overview, file details, symbol focus.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to file or directory"},
                        "focus": {"type": "string", "description": "Symbol to track across files"},
                        "max_depth": {"type": "integer", "description": "Max directory depth", "default": 3},
                    },
                    "required": ["path"],
                }
            },
            {
                "name": "list_windows",
                "description": "List available window titles for screen capture",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "screen_capture",
                "description": "Capture a screenshot of a display or window",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "display": {"type": "integer", "description": "Display number (0 for main)"},
                        "window_title": {"type": "string", "description": "Window title to capture"},
                    }
                }
            },
            {
                "name": "image_processor",
                "description": "Process an image file (resize, convert to PNG, return base64)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to image file"},
                    },
                    "required": ["path"],
                }
            },
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        if not self._initialized:
            await self.initialize()

        handlers = {
            "text_editor": self._text_editor,
            "shell": self._shell,
            "analyze": self._analyze,
            "list_windows": self._list_windows,
            "screen_capture": self._screen_capture,
            "image_processor": self._image_processor,
        }

        if name not in handlers:
            return {"error": f"Unknown tool: {name}"}

        try:
            return handlers[name](arguments)
        except Exception as e:
            return {"error": str(e)}

    def _text_editor(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle text_editor tool"""
        path = args.get("path", "")
        command = args.get("command", "")

        if not path:
            return {"error": "Missing 'path' parameter"}

        path_obj = Path(path)

        if command == "view":
            view_range = args.get("view_range")
            line_start = None
            line_end = None
            if view_range and len(view_range) == 2:
                line_start = view_range[0] - 1 if view_range[0] > 0 else None
                line_end = view_range[1] if view_range[1] > 0 else None

            try:
                if path_obj.is_dir():
                    items = []
                    for item in sorted(path_obj.iterdir()):
                        items.append(f"{'[DIR] ' if item.is_dir() else ''}{item.name}")
                    return {"content": [{"type": "text", "text": f"Directory: {path}\n\n" + "\n".join(items)}]}
                else:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    lines = content.split("\n")
                    if line_start is not None:
                        lines = lines[line_start:line_end]
                    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
            except Exception as e:
                return {"error": f"Failed to view: {e}"}

        elif command == "write":
            file_text = args.get("file_text", "")
            if file_text is None:
                return {"error": "Missing 'file_text' parameter for write command"}
            try:
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(file_text)
                return {"content": [{"type": "text", "text": f"Wrote to {path}"}]}
            except Exception as e:
                return {"error": f"Failed to write: {e}"}

        elif command == "str_replace":
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            if not old_str:
                return {"error": "Missing 'old_str' parameter for str_replace command"}
            if not new_str:
                return {"error": "Missing 'new_str' parameter for str_replace command"}
            return self._str_replace(path, old_str, new_str)

        elif command == "insert":
            insert_line = args.get("insert_line", 0)
            new_str = args.get("new_str", "")
            if not new_str:
                return {"error": "Missing 'new_str' parameter for insert command"}
            return self._insert_text(path, insert_line, new_str)

        elif command == "undo_edit":
            return self._undo_edit(path)

        else:
            return {"error": f"Unknown command: {command}"}

    def _str_replace(self, path: str, old_str: str, new_str: str) -> Dict[str, Any]:
        """Replace text in file"""
        with open(path, "r", encoding="utf-8") as f:
            current_content = f.read()

        if old_str not in current_content:
            return {"error": "Text to replace not found in file"}

        new_content = current_content.replace(old_str, new_str)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"content": [{"type": "text", "text": f"Edited {path}"}]}

    def _insert_text(self, path: str, insert_line: int, new_str: str) -> Dict[str, Any]:
        """Insert text at specific line"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.split("\n")
        if insert_line == -1 or insert_line >= len(lines):
            lines.append(new_str)
        else:
            lines.insert(insert_line, new_str)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return {"content": [{"type": "text", "text": f"Inserted at line {insert_line} in {path}"}]}

    def _undo_edit(self, path: str) -> Dict[str, Any]:
        """Undo last edit"""
        file_id = str(Path(path).resolve())
        if file_id not in self.file_history or len(self.file_history[file_id]) < 2:
            return {"error": "Nothing to undo"}

        self.file_history[file_id].pop()
        previous_content = self.file_history[file_id][-1]
        with open(path, "w", encoding="utf-8") as f:
            f.write(previous_content)
        return {"content": [{"type": "text", "text": f"Undid edit to {path}"}]}

    def _shell(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute shell command"""
        command = args.get("command", "")
        if not command:
            return {"error": "Missing 'command' parameter"}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout + result.stderr
            return {
                "content": [
                    {"type": "text", "text": output or "(no output)", "role": "user"}
                ]
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out after 60 seconds"}
        except Exception as e:
            return {"error": f"Command failed: {e}"}

    def _analyze(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze code structure"""
        path = args.get("path", "")
        focus = args.get("focus")
        max_depth = args.get("max_depth", 3)

        if not path:
            return {"error": "Missing 'path' parameter"}

        path_obj = Path(path)

        if not path_obj.exists():
            return {"error": f"Path does not exist: {path}"}

        if path_obj.is_file():
            return self._analyze_file(path_obj, focus)
        else:
            return self._analyze_directory(path_obj, focus, max_depth)

    def _analyze_file(self, path: Path, focus: Optional[str]) -> Dict[str, Any]:
        """Analyze a single file"""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = content.split("\n")

            functions = []
            classes = []
            imports = []

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("async def "):
                    func_name = stripped.split("(")[0].replace("async def ", "").replace("def ", "")
                    functions.append({"name": func_name, "line": i})
                elif stripped.startswith("class "):
                    class_name = stripped.split(":")[0].replace("class ", "")
                    classes.append({"name": class_name, "line": i})
                elif stripped.startswith("import ") or stripped.startswith("from "):
                    imports.append(stripped)

            result = [f"File: {path.name}", f"LOC: {len(lines)}", ""]
            result.append("=== Classes ===")
            for c in classes:
                result.append(f"  {c['name']} (line {c['line']})")
            result.append("")
            result.append("=== Functions ===")
            for f in functions:
                result.append(f"  {f['name']} (line {f['line']})")
            result.append("")
            result.append("=== Imports ===")
            for imp in imports[:20]:
                result.append(f"  {imp}")

            return {"content": [{"type": "text", "text": "\n".join(result)}]}
        except Exception as e:
            return {"error": f"Failed to analyze file: {e}"}

    def _analyze_directory(self, path: Path, focus: Optional[str], max_depth: int) -> Dict[str, Any]:
        """Analyze directory structure"""
        try:
            result = [f"Directory: {path}", ""]
            file_count = 0
            dir_count = 0

            for root, dirs, files in os.walk(path):
                depth = Path(root).relative_to(path).parts
                if len(depth) > max_depth:
                    dirs[:] = []
                    continue

                level = len(depth)
                indent = "  " * level

                result.append(f"{indent}{Path(root).name}/")
                dir_count += 1

                for f in sorted(files):
                    file_count += 1
                    result.append(f"{indent}  {f}")

                if level < max_depth:
                    for d in sorted(dirs):
                        result.append(f"{indent}  {d}/")

            result.insert(0, f"=== Directory Structure (max_depth={max_depth}) ===")
            result.insert(1, f"Files: {file_count}, Directories: {dir_count}")

            return {"content": [{"type": "text", "text": "\n".join(result)}]}
        except Exception as e:
            return {"error": f"Failed to analyze directory: {e}"}

    def _list_windows(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List available windows"""
        return {"content": [{"type": "text", "text": "Window listing not implemented"}]}

    def _screen_capture(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Capture screenshot"""
        return {"content": [{"type": "text", "text": "Screen capture not implemented"}]}

    def _image_processor(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Process image file"""
        path = args.get("path", "")
        if not path:
            return {"error": "Missing 'path' parameter"}

        path_obj = Path(path)
        if not path_obj.exists():
            return {"error": f"File does not exist: {path}"}

        try:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            return {
                "content": [
                    {"type": "text", "text": f"Processed image: {path}"},
                    {"type": "image", "data": data, "mimeType": "image/png"}
                ]
            }
        except Exception as e:
            return {"error": f"Failed to process image: {e}"}

    async def close(self) -> None:
        """Close extension"""
        self._initialized = False


def create_developer_extension(session_manager: Optional[SessionManager] = None) -> DeveloperPlatformExtension:
    """Create Developer Platform Extension"""
    return DeveloperPlatformExtension(session_manager)
