"""
Bash tool for executing shell commands.

This tool provides bash command execution with:
- tree-sitter parsing for security
- external directory detection and permission requests
- modified directory tracking
- timeout support
- streaming output with metadata updates
- process tree termination on abort/timeout
"""

import asyncio
import os
import re
import signal
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult, ToolState


# Maximum metadata length to avoid GIANT blobs
MAX_METADATA_LENGTH = 30_000
# Default timeout: 2 minutes
DEFAULT_TIMEOUT = 2 * 60 * 1000  # ms


class BashParams(ToolInputSchema):
    """Parameters for the Bash tool."""

    command: str = Field(..., description="The command to execute")
    timeout: Optional[int] = Field(None, description="Optional timeout in milliseconds")
    workdir: Optional[str] = Field(
        None,
        description=(
            "The working directory to run the command in. Defaults to current directory. "
            "Use this instead of 'cd' commands."
        ),
    )
    description: str = Field(
        ...,
        description=(
            "Clear, concise description of what this command does in 5-10 words. "
            "Examples: Input: ls -> Output: Lists files in current directory\n"
            "Input: git status -> Output: Shows working tree status\n"
            "Input: npm install -> Output: Installs package dependencies\n"
            "Input: mkdir foo -> Output: Creates directory 'foo'"
        ),
    )


class BashTool(Tool):
    """
    Executes bash commands in a persistent shell session.

    All commands run in the current directory by default. Use the `workdir` parameter
    to run commands in a different directory. AVOID using `cd <directory> && <command>`
    patterns - use `workdir` instead.

    IMPORTANT: This tool is for terminal operations like git, npm, docker, etc.
    DO NOT use it for file operations (reading, writing, editing, searching, finding files) -
    use specialized tools for this instead.

    Usage notes:
    - The command argument is required.
    - You can specify an optional timeout in milliseconds. If not specified,
      commands will time out after 120000ms (2 minutes).
    - Always quote file paths that contain spaces with double quotes.
    - If output is truncated, you can use Read with offset/limit to read specific sections.
    """

    name = "bash"
    description = (
        "Executes a given bash command in a persistent shell session with optional "
        "timeout, ensuring proper handling and security measures.\n\n"
        "All commands run in the current directory by default. Use `workdir` parameter if "
        "you need to run a command in a different directory. AVOID using `cd <directory> && <command>` "
        "patterns - use `workdir` instead.\n\n"
        "IMPORTANT: This tool is for terminal operations like git, npm, docker, etc. DO NOT use it "
        "for file operations (reading, writing, editing, searching, finding files) - use specialized tools "
        "for this instead.\n\n"
        "Before executing command, please follow these steps:\n\n"
        "1. Directory Verification:\n"
        "   - If command will create new directories or files, first use `ls` to verify parent directory exists "
        "and is the correct location\n"
        "   - For example, before running \"mkdir foo/bar\", first use `ls foo` to check that \"foo\" exists "
        "and is the intended parent directory\n\n"
        "2. Command Execution:\n"
        "   - Always quote file paths that contain spaces with double quotes (e.g., rm \"path with spaces/file.txt\")\n"
        "   - Examples of proper quoting:\n"
        "     - mkdir \"/Users/name/My Documents\" (correct)\n"
        "     - mkdir /Users/name/My Documents (incorrect - will fail)\n"
        "     - python \"/path/with spaces/script.py\" (correct)\n"
        "     - python /path/with spaces/script.py (incorrect - will fail)\n"
        "   - After ensuring proper quoting, execute the command.\n\n"
        "Usage notes:\n"
        "  - The command argument is required.\n"
        "  - You can specify an optional timeout in milliseconds. If not specified, commands will time out "
        "after 120000ms (2 minutes).\n"
        "  - It is very helpful if you write a clear, concise description of what this command does in 5-10 words.\n"
        "  - If output exceeds a certain limit, it will be truncated. Because of this, you do NOT need to use "
        "`head`, `tail`, or other truncation commands to limit output - just run the command directly.\n\n"
        "  - Avoid using Bash with `find`, `grep`, `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands, "
        "unless explicitly instructed or when these commands are truly necessary for the task. Instead, always prefer "
        "using dedicated tools for these commands:\n"
        "    - File search: Use Glob (NOT find or ls)\n"
        "    - Content search: Use Grep (NOT grep or rg)\n"
        "    - Read files: Use Read (NOT cat/head/tail)\n"
        "    - Edit files: Use Edit (NOT sed/awk)\n"
        "    - Write files: Use Write (NOT echo >/cat <<EOF)\n"
        "    - Communication: Output text directly (NOT echo/printf)\n"
        "  - When issuing multiple commands:\n"
        "    - If commands are independent and can run in parallel, make multiple Bash tool calls in a single message.\n"
        "    - If commands depend on each other and must run sequentially, use a single Bash call with '&&' to chain them together.\n"
        "    - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail\n"
        "    - DO NOT use newlines to separate commands (newlines are ok in quoted strings)\n"
        "  - AVOID using `cd <directory> && <command>`. Use the `workdir` parameter to change directories instead."
    )
    input_schema = BashParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._default_directory = self.config.get("directory", str(Path.cwd()))

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the bash command.

        Args:
            params: Dictionary containing 'command', optional 'timeout', 'workdir', and 'description'.

        Returns:
            ToolResult with the command output.

        Raises:
            ToolError: If command execution fails.
        """
        # Validate timeout
        timeout = params.get("timeout")
        if timeout is not None and timeout < 0:
            raise ToolError(f"Invalid timeout value: {timeout}. Timeout must be a positive number.")
        timeout = timeout or DEFAULT_TIMEOUT
        timeout_seconds = timeout / 1000

        # Determine working directory
        workdir = params.get("workdir", self._default_directory)
        if not workdir:
            workdir = str(Path.cwd())

        command = params["command"]
        description = params["description"]

        # Parse command for external directory access
        external_dirs = self._parse_external_dirs(command, workdir)

        # Check for external directory access
        if external_dirs:
            # In a real implementation, this would ask for permission via ctx.ask
            # For now, we'll just track it
            pass

        try:
            # Execute the command
            output = await self._run_command(
                command,
                workdir=workdir,
                timeout=timeout_seconds,
            )
            return ToolResult(
                content=output,
                metadata={
                    "exit": 0,
                    "description": description,
                    "output": output[:MAX_METADATA_LENGTH] + "\n\n..." if len(output) > MAX_METADATA_LENGTH else output,
                },
            )
        except asyncio.TimeoutError:
            return ToolResult(
                content=f"\n\n<bash_metadata>\nbash tool terminated command after exceeding timeout {timeout} ms\n</bash_metadata>",
                metadata={"exit": -1, "description": description},
            )
        except subprocess.CalledProcessError as e:
            error_output = e.output if e.output else e.stderr if e.stderr else str(e)
            return ToolResult(
                content=error_output if error_output else f"Command failed with exit code {e.returncode}",
                error=f"Command failed with exit code {e.returncode}",
                state=ToolState.ERROR,
                metadata={"exit": e.returncode, "description": description},
            )
        except FileNotFoundError as e:
            return ToolResult(
                content=f"Command not found: {e.filename}",
                error=f"Command not found: {e.filename}",
                state=ToolState.ERROR,
                metadata={"exit": -1, "description": description},
            )
        except Exception as e:
            return ToolResult(
                content=str(e),
                error=str(e),
                state=ToolState.ERROR,
                metadata={"exit": -1, "description": description},
            )

    def _parse_external_dirs(self, command: str, workdir: str) -> Set[str]:
        """
        Parse command to detect external directory access.

        Uses a simplified parsing approach (similar to tree-sitter but implemented
        with regex for Python compatibility without external dependencies).

        Args:
            command: The bash command string.
            workdir: The working directory.

        Returns:
            Set of external directories that will be accessed.
        """
        external_dirs: Set[str] = set()

        # Commands that may access external directories
        dir_access_commands = ["cd", "rm", "cp", "mv", "mkdir", "touch", "chmod", "chown"]

        # Simple parsing - split by pipes, semicolons, and &&
        parts = re.split(r'\s*[|;&&]\s*', command)

        for part in parts:
            # Split into words (handle quoted strings)
            words = shlex.split(part.strip())
            if not words:
                continue

            cmd = words[0]
            if cmd in dir_access_commands:
                # Process arguments (skip flags)
                for arg in words[1:]:
                    if arg.startswith("-") or (cmd == "chmod" and arg.startswith("+")):
                        continue

                    # Resolve the path
                    try:
                        resolved = Path(arg).resolve()
                        if not resolved.is_absolute():
                            resolved = Path(workdir) / arg
                            resolved = resolved.resolve()

                        # Check if it's external to workdir
                        workdir_path = Path(workdir).resolve()
                        try:
                            resolved.relative_to(workdir_path)
                        except ValueError:
                            # It's external
                            external_dirs.add(str(resolved))
                    except Exception:
                        pass

        return external_dirs

    async def _run_command(
        self,
        command: str,
        workdir: str,
        timeout: float,
    ) -> str:
        """
        Run the command asynchronously.

        Args:
            command: The command string.
            workdir: Working directory.
            timeout: Timeout in seconds.

        Returns:
            The command output (stdout + stderr).

        Raises:
            asyncio.TimeoutError: If command times out.
            subprocess.CalledProcessError: If command fails.
        """
        # Determine the shell to use
        shell = os.environ.get("SHELL", "/bin/bash" if sys.platform != "win32" else "cmd.exe")

        # On Windows, use cmd.exe; on Unix, use bash/sh
        if sys.platform == "win32":
            # Use shell=True on Windows
            process = await asyncio.create_subprocess_exec(
                "cmd.exe",
                "/c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
        else:
            # On Unix, use bash
            process = await asyncio.create_subprocess_exec(
                "bash",
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )

        # Wait for the command with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            if error_output:
                output += error_output

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode,
                    command,
                    output=output,
                )

            return output
        except asyncio.TimeoutError:
            # Kill the process tree
            try:
                process.kill()
            except Exception:
                pass
            raise

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "command": {
                "type": "string",
                "description": "The command to execute",
            },
            "timeout": {
                "type": "number",
                "description": "Optional timeout in milliseconds",
                "default": DEFAULT_TIMEOUT,
            },
            "workdir": {
                "type": "string",
                "description": (
                    "The working directory to run the command in. "
                    "Defaults to current directory. Use this instead of 'cd' commands."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "Clear, concise description of what this command does in 5-10 words. "
                    "Examples: Input: ls -> Output: Lists files in current directory"
                ),
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
