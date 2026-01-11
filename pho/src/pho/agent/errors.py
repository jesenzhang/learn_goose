"""
Unified Error Handling for Pho Framework.

Provides consistent exception types and error handling patterns across all modules.
"""

from typing import Optional, Dict, Any, List
from enum import Enum


class ErrorCode(str, Enum):
    """Standard error codes"""
    # Configuration errors (1xxx)
    CONFIG_INVALID = "CONFIG_100"
    CONFIG_MISSING = "CONFIG_101"
    CONFIG_VALIDATION = "CONFIG_102"

    # Agent errors (2xxx)
    AGENT_INIT_FAILED = "AGENT_200"
    AGENT_EXECUTION_FAILED = "AGENT_201"
    AGENT_NOT_INITIALIZED = "AGENT_202"
    AGENT_TIMEOUT = "AGENT_203"

    # Tool errors (3xxx)
    TOOL_NOT_FOUND = "TOOL_300"
    TOOL_EXECUTION_FAILED = "TOOL_301"
    TOOL_BLOCKED = "TOOL_302"
    TOOL_INVALID_ARGS = "TOOL_303"

    # LLM errors (4xxx)
    LLM_CONNECTION_FAILED = "LLM_400"
    LLM_RATE_LIMITED = "LLM_401"
    LLM_INVALID_RESPONSE = "LLM_402"
    LLM_TIMEOUT = "LLM_403"

    # Workflow errors (5xxx)
    WORKFLOW_INVALID = "WORKFLOW_500"
    WORKFLOW_EXECUTION_FAILED = "WORKFLOW_501"
    WORKFLOW_NOT_FOUND = "WORKFLOW_502"

    # System errors (9xxx)
    INTERNAL_ERROR = "SYS_900"
    NOT_IMPLEMENTED = "SYS_901"


class PhoException(Exception):
    """
    Base exception for all Pho framework errors.

    Provides consistent error structure with:
    - Error code for categorization
    - User-friendly message
    - Detailed context for debugging
    - Suggestions for resolution
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.suggestion = suggestion
        self.__cause__ = cause
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses"""
        return {
            "error": self.code.value,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        if self.suggestion:
            return f"{self.message} Suggestion: {self.suggestion}"
        return self.message


# ============================================================================
# Configuration Errors
# ============================================================================

class ConfigException(PhoException):
    """Base exception for configuration errors"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None
    ):
        super().__init__(
            message=message,
            code=ErrorCode.CONFIG_INVALID,
            details=details,
            suggestion=suggestion
        )


class ConfigValidationException(ConfigException):
    """Raised when configuration validation fails"""

    def __init__(
        self,
        field: str,
        value: Any,
        reason: str,
        suggestion: Optional[str] = None
    ):
        super().__init__(
            message=f"Configuration validation failed for field '{field}'",
            details={"field": field, "value": str(value), "reason": reason},
            suggestion=suggestion or f"Check the value for '{field}' in your configuration"
        )


class MissingConfigException(ConfigException):
    """Raised when required configuration is missing"""

    def __init__(
        self,
        field: str,
        suggestion: Optional[str] = None
    ):
        super().__init__(
            message=f"Required configuration field '{field}' is missing",
            details={"field": field},
            suggestion=suggestion or f"Provide a value for '{field}' in your configuration"
        )


# ============================================================================
# Agent Errors
# ============================================================================

class AgentException(PhoException):
    """Base exception for agent-related errors"""

    def __init__(
        self,
        message: str,
        agent_style: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None
    ):
        if details is None:
            details = {}
        if agent_style:
            details["agent_style"] = agent_style

        super().__init__(
            message=message,
            code=ErrorCode.AGENT_EXECUTION_FAILED,
            details=details,
            suggestion=suggestion
        )


class AgentInitException(AgentException):
    """Raised when agent initialization fails"""

    def __init__(
        self,
        style: str,
        reason: str,
        suggestion: Optional[str] = None
    ):
        super().__init__(
            message=f"Failed to initialize {style} agent: {reason}",
            agent_style=style,
            details={"reason": reason},
            suggestion=suggestion or f"Check the configuration for {style} agent"
        )


class AgentExecutionException(AgentException):
    """Raised when agent execution fails"""

    def __init__(
        self,
        message: str,
        agent_style: Optional[str] = None,
        step: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        if details is None:
            details = {}
        if step:
            details["step"] = step

        super().__init__(
            message=message,
            agent_style=agent_style,
            details=details,
            suggestion="Check the agent logs for more details"
        )


# ============================================================================
# Tool Errors
# ============================================================================

class ToolException(PhoException):
    """Base exception for tool-related errors"""

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None
    ):
        if details is None:
            details = {}
        if tool_name:
            details["tool_name"] = tool_name

        super().__init__(
            message=message,
            code=ErrorCode.TOOL_EXECUTION_FAILED,
            details=details,
            suggestion=suggestion
        )


class ToolNotFoundException(ToolException):
    """Raised when a tool is not found"""

    def __init__(
        self,
        tool_name: str,
        available_tools: Optional[List[str]] = None
    ):
        details = {"tool_name": tool_name}
        if available_tools:
            details["available_tools"] = available_tools

        super().__init__(
            message=f"Tool '{tool_name}' not found",
            tool_name=tool_name,
            details=details,
            suggestion=f"Available tools: {', '.join(available_tools or [])}"
        )


class ToolExecutionException(ToolException):
    """Raised when tool execution fails"""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        args: Optional[Dict[str, Any]] = None
    ):
        details = {"tool_name": tool_name, "reason": reason}
        if args:
            details["args"] = str(args)

        super().__init__(
            message=f"Tool '{tool_name}' execution failed: {reason}",
            tool_name=tool_name,
            details=details,
            suggestion="Check tool arguments and permissions"
        )


class ToolBlockedException(ToolException):
    """Raised when tool execution is blocked by inspector"""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        inspector: Optional[str] = None
    ):
        details = {"tool_name": tool_name, "reason": reason}
        if inspector:
            details["inspector"] = inspector

        super().__init__(
            message=f"Tool '{tool_name}' blocked: {reason}",
            tool_name=tool_name,
            details=details,
            suggestion="Modify the tool call or request permission"
        )


# ============================================================================
# LLM Errors
# ============================================================================

class LLMException(PhoException):
    """Base exception for LLM-related errors"""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None
    ):
        if details is None:
            details = {}
        if provider:
            details["provider"] = provider

        super().__init__(
            message=message,
            code=ErrorCode.LLM_CONNECTION_FAILED,
            details=details,
            suggestion=suggestion
        )


class LLMConnectionException(LLMException):
    """Raised when LLM connection fails"""

    def __init__(
        self,
        provider: str,
        reason: str
    ):
        super().__init__(
            message=f"LLM connection failed for provider '{provider}': {reason}",
            provider=provider,
            details={"reason": reason},
            suggestion="Check API key, network connection, and provider status"
        )


class LLMRateLimitException(LLMException):
    """Raised when LLM rate limit is hit"""

    def __init__(
        self,
        provider: str,
        retry_after: Optional[float] = None
    ):
        details = {"provider": provider}
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message=f"Rate limit exceeded for provider '{provider}'",
            provider=provider,
            details=details,
            suggestion=f"Wait {retry_after}s before retrying" if retry_after else "Implement exponential backoff"
        )


class LLMTimeoutException(LLMException):
    """Raised when LLM request times out"""

    def __init__(
        self,
        provider: str,
        timeout: float
    ):
        super().__init__(
            message=f"LLM request timed out after {timeout}s for provider '{provider}'",
            provider=provider,
            details={"timeout_seconds": timeout},
            suggestion="Increase timeout or reduce input size"
        )


# ============================================================================
# Workflow Errors
# ============================================================================

class WorkflowException(PhoException):
    """Base exception for workflow-related errors"""

    def __init__(
        self,
        message: str,
        workflow_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None
    ):
        if details is None:
            details = {}
        if workflow_id:
            details["workflow_id"] = workflow_id

        super().__init__(
            message=message,
            code=ErrorCode.WORKFLOW_EXECUTION_FAILED,
            details=details,
            suggestion=suggestion
        )


class WorkflowValidationException(WorkflowException):
    """Raised when workflow validation fails"""

    def __init__(
        self,
        message: str,
        errors: List[str]
    ):
        super().__init__(
            message=f"Workflow validation failed: {message}",
            details={"errors": errors},
            suggestion="Fix the validation errors before executing the workflow"
        )


class WorkflowNotFoundException(WorkflowException):
    """Raised when a workflow is not found"""

    def __init__(self, workflow_id: str):
        super().__init__(
            message=f"Workflow '{workflow_id}' not found",
            workflow_id=workflow_id,
            suggestion="Check the workflow ID or create the workflow first"
        )


# ============================================================================
# Utility Functions
# ============================================================================

def handle_exception(
    exc: Exception,
    context: Optional[str] = None,
    reraise: bool = False
) -> PhoException:
    """
    Convert any exception to a PhoException.

    Args:
        exc: The exception to handle
        context: Optional context string for error message
        reraise: Whether to reraise after conversion

    Returns:
        PhoException instance
    """
    if isinstance(exc, PhoException):
        return exc

    # Convert common exceptions
    if isinstance(exc, ValueError):
        return PhoException(
            message=f"Invalid value: {str(exc)}",
            code=ErrorCode.CONFIG_INVALID,
            details={"original_error": str(exc)}
        )

    if isinstance(exc, KeyError):
        return PhoException(
            message=f"Missing required key: {str(exc)}",
            code=ErrorCode.CONFIG_MISSING,
            details={"key": str(exc)}
        )

    if isinstance(exc, ConnectionError):
        return LLMConnectionException(
            provider="unknown",
            reason=str(exc)
        )

    if isinstance(exc, TimeoutError):
        return LLMTimeoutException(
            provider="unknown",
            timeout=0
        )

    # Default wrapper
    return PhoException(
        message=f"{context + ': ' if context else ''}{str(exc)}",
        code=ErrorCode.INTERNAL_ERROR,
        details={"original_type": type(exc).__name__},
        cause=exc
    )


__all__ = [
    # Base
    "ErrorCode",
    "PhoException",

    # Config
    "ConfigException",
    "ConfigValidationException",
    "MissingConfigException",

    # Agent
    "AgentException",
    "AgentInitException",
    "AgentExecutionException",

    # Tool
    "ToolException",
    "ToolNotFoundException",
    "ToolExecutionException",
    "ToolBlockedException",

    # LLM
    "LLMException",
    "LLMConnectionException",
    "LLMRateLimitException",
    "LLMTimeoutException",

    # Workflow
    "WorkflowException",
    "WorkflowValidationException",
    "WorkflowNotFoundException",

    # Utils
    "handle_exception",
]
