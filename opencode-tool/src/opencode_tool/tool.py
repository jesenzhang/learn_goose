"""
Base tool class and types for opencode-tool.

This module defines the core Tool interface and related types
used across all tool implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type, get_type_hints

from pydantic import BaseModel, Field


class ToolState(str, Enum):
    """State of a tool execution."""
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolInfo:
    """Metadata about a tool."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Return the tool identifier."""
        return self.name


@dataclass
class ToolResult:
    """Result of a tool execution."""
    content: str = ""
    error: Optional[str] = None
    state: ToolState = ToolState.COMPLETED
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "content": self.content,
            "error": self.error,
            "state": self.state.value,
            "metadata": self.metadata,
        }


class ToolError(Exception):
    """Base exception for tool errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ToolInputSchema(BaseModel):
    """Base model for tool input validation."""

    class Config:
        extra = "forbid"


class Tool(ABC):
    """
    Abstract base class for all tools.

    Each tool should:
    1. Define its input parameters as a Pydantic model or in the schema
    2. Implement the execute() method
    3. Set name and description
    """

    name: str = ""
    description: str = ""
    input_schema: Optional[Type[ToolInputSchema]] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the tool.

        Args:
            config: Optional configuration dictionary for the tool.
        """
        self.config = config or {}
        self._build_schema_from_hints()

    def _build_schema_from_hints(self) -> None:
        """Build input schema from execute method type hints if not provided."""
        if self.input_schema is not None:
            return

        # Try to get type hints from execute method
        execute_hints = get_type_hints(self.execute)

        # Extract 'params' hint if it exists and is a BaseModel
        if "params" in execute_hints:
            param_type = execute_hints["params"]
            if isinstance(param_type, type) and issubclass(param_type, BaseModel):
                self.input_schema = param_type

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters: Dict[str, Any] = {}

        if self.input_schema:
            parameters = {
                name: {
                    "type": field_info.annotation.__name__ if hasattr(field_info.annotation, "__name__") else str(field_info.annotation),
                    "description": field_info.description or "",
                    "default": field_info.default if field_info.default is not Field.default else None,
                }
                for name, field_info in self.input_schema.model_fields.items()
            }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool with the given parameters.

        Args:
            params: Tool parameters as a dictionary.

        Returns:
            ToolResult containing the execution result.

        Raises:
            ToolError: If the tool execution fails.
        """
        pass

    async def validate(self, params: Dict[str, Any]) -> None:
        """
        Validate tool parameters.

        Args:
            params: Parameters to validate.

        Raises:
            ValidationError: If parameters are invalid.
        """
        if self.input_schema:
            self.input_schema.model_validate(params)

    async def run(self, params: Dict[str, Any]) -> ToolResult:
        """
        Run the tool with validation and error handling.

        Args:
            params: Tool parameters.

        Returns:
            ToolResult with execution result or error.
        """
        try:
            await self.validate(params)
            result = await self.execute(params)
            return result
        except ToolError as e:
            return ToolResult(
                content="",
                error=e.message,
                state=ToolState.ERROR,
                metadata={"details": e.details},
            )
        except Exception as e:
            return ToolResult(
                content="",
                error=str(e),
                state=ToolState.ERROR,
            )


def define_tool(
    name: str,
    description: str,
    schema: Optional[Type[ToolInputSchema]] = None,
) -> callable:
    """
    Decorator for defining a tool class.

    Args:
        name: Tool name.
        description: Tool description.
        schema: Optional input schema class.

    Returns:
        Decorator function.
    """

    def decorator(cls: Type[Tool]) -> Type[Tool]:
        cls.name = name
        cls.description = description
        if schema is not None:
            cls.input_schema = schema
        return cls

    return decorator


class InvalidTool(Tool):
    """Tool that represents an invalid or unknown tool request."""

    name = "invalid"
    description = "Invalid tool - used for unknown tool names"

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            content="",
            error=f"Unknown tool: {params.get('tool_name', 'unknown')}",
            state=ToolState.ERROR,
        )
