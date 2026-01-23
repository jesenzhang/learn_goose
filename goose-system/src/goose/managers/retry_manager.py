"""
Retry Manager

Enhanced retry logic with SuccessCheck and on_failure command support.
Reference: goose-rs agents/retry.rs

Features:
- RetryResult enum (Skipped, MaxAttemptsReached, SuccessChecksPassed, Retried)
- SuccessCheck (Shell command validation)
- on_failure command support with timeout
- Timeout configuration for shell commands
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import asyncio
import os
import platform


class RetryResult(Enum):
    """Result of a retry logic evaluation"""
    SKIPPED = "skipped"
    MAX_ATTEMPTS_REACHED = "max_attempts_reached"
    SUCCESS_CHECKS_PASSED = "success_checks_passed"
    RETRIED = "retried"


@dataclass
class SuccessCheck:
    """Base class for success checks"""
    type: str = ""

    async def check(self) -> bool:
        """Execute the success check"""
        return False

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SuccessCheck":
        """Create SuccessCheck from dictionary"""
        check_type = data.get("type", "shell")
        if check_type == "shell":
            check = ShellSuccessCheck()
            check.type = "shell"
            check.command = data.get("command", "")
            return check
        raise ValueError(f"Unknown success check type: {check_type}")


@dataclass
class ShellSuccessCheck(SuccessCheck):
    """Execute a shell command and check its exit status"""
    command: str = ""

    def __post_init__(self):
        self.type = "shell"

    async def check(self) -> bool:
        """Execute shell command and check exit status"""
        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        except Exception:
            return False


@dataclass
class RetryConfig:
    """Configuration for retry logic in recipe execution"""
    max_retries: int = 3
    checks: List[SuccessCheck] = field(default_factory=list)
    on_failure: Optional[str] = None
    timeout_seconds: Optional[int] = None
    on_failure_timeout_seconds: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetryConfig":
        """Create RetryConfig from dictionary"""
        checks = []
        for check_data in data.get("checks", []):
            checks.append(SuccessCheck.from_dict(check_data))

        return cls(
            max_retries=data.get("max_retries", 3),
            checks=checks,
            on_failure=data.get("on_failure"),
            timeout_seconds=data.get("timeout_seconds"),
            on_failure_timeout_seconds=data.get("on_failure_timeout_seconds")
        )

    def validate(self) -> tuple[bool, str]:
        """Validate the retry configuration values"""
        if self.max_retries < 0:
            return False, "max_retries must be >= 0"

        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            return False, "timeout_seconds must be > 0 if specified"

        if self.on_failure_timeout_seconds is not None and self.on_failure_timeout_seconds <= 0:
            return False, "on_failure_timeout_seconds must be > 0 if specified"

        return True, ""


class ExecutionResult:
    """Result of a shell command execution"""
    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        return_code: int = -1,
        timed_out: bool = False
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.timed_out = timed_out


async def execute_shell_command(
    command: str,
    timeout_seconds: Optional[int] = None
) -> ExecutionResult:
    """
    Execute a shell command with cross-platform compatibility and optional timeout.

    Args:
        command: The shell command to execute
        timeout_seconds: Optional timeout in seconds

    Returns:
        ExecutionResult with success status, stdout, stderr, and return code
    """
    timeout = timeout_seconds or 300  # Default 5 minutes

    try:
        if platform.system() == "Windows":
            full_command = f"cmd /C {command}"
        else:
            full_command = f"sh -c '{command}'"

        env = dict(os.environ)
        env["GOOSE_TERMINAL"] = "1"

        process = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")
            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode or 0
            )
        except asyncio.TimeoutError:
            process.kill()
            return ExecutionResult(
                success=False,
                return_code=-1,
                timed_out=True
            )

    except Exception as e:
        return ExecutionResult(
            success=False,
            stderr=str(e),
            return_code=-1
        )


async def execute_on_failure_command(
    command: str,
    timeout_seconds: Optional[int] = None
) -> ExecutionResult:
    """
    Execute an on_failure command.

    Args:
        command: The shell command to execute on failure
        timeout_seconds: Optional timeout in seconds (default 10 minutes)

    Returns:
        ExecutionResult with success status
    """
    timeout = timeout_seconds or 600  # Default 10 minutes
    return await execute_shell_command(command, timeout)


async def execute_success_checks(
    checks: List[SuccessCheck]
) -> bool:
    """
    Execute all success checks and return true if all pass.

    Args:
        checks: List of success checks to execute

    Returns:
        True if all checks pass, False otherwise
    """
    for check in checks:
        if isinstance(check, ShellSuccessCheck):
            result = await check.check()
            if not result:
                return False
    return True


class RetryManager:
    """
    Manages retry state and operations for agent execution.

    Features:
    - Retry attempt tracking
    - SuccessCheck validation
    - on_failure command execution
    - Conversation reset for retry
    """

    DEFAULT_RETRY_TIMEOUT_SECONDS = 300  # 5 minutes
    DEFAULT_ON_FAILURE_TIMEOUT_SECONDS = 600  # 10 minutes

    def __init__(self):
        self._attempts: int = 0
        self._lock = asyncio.Lock()

    async def reset_attempts(self) -> None:
        """Reset the retry attempts counter to 0"""
        async with self._lock:
            self._attempts = 0

    async def increment_attempts(self) -> int:
        """Increment the retry attempts counter and return the new value"""
        async with self._lock:
            self._attempts += 1
            return self._attempts

    async def get_attempts(self) -> int:
        """Get the current retry attempts count"""
        async with self._lock:
            return self._attempts

    async def handle_retry_logic(
        self,
        conversation: Any,
        retry_config: Optional[RetryConfig],
        initial_messages: List[Any],
        final_output_tool: Optional[Any] = None
    ) -> RetryResult:
        """
        Handle retry logic for agent execution.

        Args:
            conversation: Current conversation state
            retry_config: Retry configuration
            initial_messages: Initial message history for reset
            final_output_tool: Optional final output tool for state reset

        Returns:
            RetryResult indicating the outcome
        """
        if retry_config is None:
            return RetryResult.SKIPPED

        if retry_config.checks:
            success = await execute_success_checks(retry_config.checks)
            if success:
                return RetryResult.SUCCESS_CHECKS_PASSED

        current_attempts = await self.get_attempts()
        if current_attempts >= retry_config.max_retries:
            return RetryResult.MAX_ATTEMPTS_REACHED

        if retry_config.on_failure:
            await execute_on_failure_command(
                retry_config.on_failure,
                retry_config.on_failure_timeout_seconds
            )

        await self._reset_status_for_retry(conversation, initial_messages, final_output_tool)

        await self.increment_attempts()

        return RetryResult.RETRIED

    async def _reset_status_for_retry(
        self,
        conversation: Any,
        initial_messages: List[Any],
        final_output_tool: Optional[Any] = None
    ) -> None:
        """Reset message history and final output tool state for retry"""
        if conversation is not None:
            if hasattr(conversation, 'reset_to_messages'):
                conversation.reset_to_messages(initial_messages)
            elif hasattr(conversation, 'messages'):
                conversation.messages = list(initial_messages)

        if final_output_tool is not None and hasattr(final_output_tool, 'reset'):
            final_output_tool.reset()

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        retry_config: Optional[RetryConfig] = None,
        **kwargs
    ) -> tuple[Any, RetryResult]:
        """
        Execute a function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            retry_config: Optional retry configuration
            **kwargs: Keyword arguments for the function

        Returns:
            Tuple of (result, RetryResult)
        """
        retry_result = await self.handle_retry_logic(
            None,  # conversation
            retry_config,
            []  # initial_messages
        )

        if retry_result in (RetryResult.SKIPPED, RetryResult.SUCCESS_CHECKS_PASSED):
            result = await func(*args, **kwargs)
            return result, retry_result

        if retry_result == RetryResult.MAX_ATTEMPTS_REACHED:
            raise RuntimeError(f"Maximum retry attempts exceeded")

        result = await func(*args, **kwargs)
        return result, RetryResult.RETRIED


async def with_retry(
    func: Callable,
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs
) -> tuple[Any, RetryResult]:
    """
    Convenience function for executing with retry logic.

    Usage:
        result, status = await with_retry(
            my_function,
            arg1, arg2,
            config=RetryConfig(max_retries=5),
            kwarg1=value1
        )
    """
    manager = RetryManager()
    return await manager.execute_with_retry(func, *args, config=config, **kwargs)
