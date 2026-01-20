"""
MCP (Model Context Protocol) Adapter for opencode-tool.

This module provides MCP compatibility layer for opencode-tool,
allowing tools to be used as MCP servers similar to goose-rs.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type, Union
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# MCP Error Types
# ============================================================================

class ErrorCode(str):
    """MCP error codes."""
    INVALID_PARAMS = -32600
    INTERNAL_ERROR = -32603
    NOT_FOUND = -32601
    PERMISSION_DENIED = -32602


class ErrorData(BaseModel):
    """Error data structure."""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


# ============================================================================
# Tool Base Class
# ============================================================================

class MCPTool(ABC):
    """
    Base class for MCP tools compatible with goose-rs pattern.

    Each tool should:
    1. Define input parameters as a Pydantic model
    2. Implement execute() method
    3. Set name and description
    """

    name: str = ""
    description: str = ""
    input_schema: Optional[Type[BaseModel]] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize tool.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}

    @property
    def schema(self) -> Dict[str, Any]:
        """
        Get JSON Schema for tool input.

        Returns:
            JSON Schema dictionary
        """
        if self.input_schema is None:
            return {"type": "object", "properties": {}, "required": []}

        schema = self.input_schema.model_json_schema()

        # Ensure required fields
        if "required" not in schema:
            schema["required"] = []
        elif not isinstance(schema["required"], list):
            schema["required"] = list(schema["required"])

        return schema

    def validate_params(self, params: Dict[str, Any]) -> BaseModel:
        """
        Validate parameters against input schema.

        Args:
            params: Raw parameter dictionary

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If validation fails
        """
        if self.input_schema is None:
            return params

        try:
            return self.input_schema.model_validate(params)
        except Exception as e:
            raise ValueError(f"Invalid parameters: {str(e)}")

    @abstractmethod
    async def execute(self, params: BaseModel) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Execute the tool.

        Args:
            params: Validated parameters (Pydantic model)

        Returns:
            Tool result as string, dict, or list of content dicts

        Raises:
            Exception: If execution fails
        """
        pass

    async def run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run tool with validation and error handling.

        Args:
            params: Raw parameter dictionary

        Returns:
            MCP-formatted response:
            {
                "content": [{"type": "text", "text": "result"}]
            } or
            {
                "error": {"code": -32603, "message": "error message"}
            }
        """
        try:
            validated_params = self.validate_params(params)
            result = await self.execute(validated_params)

            # Normalize result to MCP content format
            if isinstance(result, list):
                # Already in content format
                return {"content": result}
            elif isinstance(result, dict):
                # Check if it's already in MCP format
                if "content" in result or "error" in result:
                    return result
                # Regular dict, convert to text content
                return {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False)
                    }]
                }
            else:
                # String or other primitive
                return {
                    "content": [{
                        "type": "text",
                        "text": str(result)
                    }]
                }

        except ValueError as e:
            logger.error(f"Validation error in {self.name}: {e}")
            return {
                "error": ErrorData(
                    code=ErrorCode.INVALID_PARAMS,
                    message=str(e)
                ).model_dump()
            }
        except Exception as e:
            logger.error(f"Execution error in {self.name}: {e}", exc_info=True)
            return {
                "error": ErrorData(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(e)
                ).model_dump()
            }


# ============================================================================
# Builtin Tool Registry
# ============================================================================

class BuiltinDef:
    """Definition of a builtin tool."""

    def __init__(
        self,
        name: str,
        description: str,
        tool_class: Type[MCPTool]
    ):
        self.name = name
        self.description = description
        self.tool_class = tool_class


class BuiltinRegistry:
    """
    Registry for builtin MCP tools.

    Similar to goose-rs' BUILTIN_EXTENSIONS HashMap.
    """

    def __init__(self):
        self._tools: Dict[str, BuiltinDef] = {}

    def register(self, definition: BuiltinDef):
        """
        Register a builtin tool.

        Args:
            definition: Builtin tool definition
        """
        self._tools[definition.name] = definition

    def get(self, name):
        """Get a builtin tool by name.

        Args:
            name: fully qualified name of tool to create
            config: Optional configuration for tool

        Returns:
            Tool instance or None
        """
        if name not in self._tools:
            return None

        definition = self._tools[name]
        return definition.tool_class(config)

    def all(self) -> Dict[str, BuiltinDef]:
        """
        Get all registered tools.

        Returns:
            Dictionary of name -> definition
        """
        return self._tools.copy()

    def names(self) -> List[str]:
        """
        Get all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def has(self, name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            name: Tool name

        Returns:
            True if tool exists
        """
        return name in self._tools


# Global registry
_builtin_registry: Optional[BuiltinRegistry] = None


def get_builtin_registry() -> BuiltinRegistry:
    """
    Get the global builtin registry.

    Returns:
        BuiltinRegistry singleton instance
    """
    global _builtin_registry
    if _builtin_registry is None:
        _builtin_registry = BuiltinRegistry()
    return _builtin_registry


def register_builtin(name: str, description: str):
    """
    Decorator to register a tool class as builtin.

    Args:
        name: Tool name
        description: Tool description

    Example:
        @register_builtin("bash", "Execute shell commands")
        class BashTool(MCPTool):
            class Params(BaseModel):
                command: str

            input_schema = Params
            name = "bash"
            description = "Execute shell commands"

            async def execute(self, params: Params) -> str:
                return "Command executed"
    """
    def decorator(cls: Type[MCPTool]) -> Type[MCPTool]:
        registry = get_builtin_registry()
        registry.register(BuiltinDef(
            name=name,
            description=description,
            tool_class=cls
        ))
        return cls

    return decorator


def get_builtin_tool(name: str, config: Optional[Dict[str, Any]] = None) -> Optional[MCPTool]:
    """
    Get a builtin tool instance by name.

    Args:
        name: Tool name
        config: Optional configuration

    Returns:
        Tool instance or None
    """
    registry = get_builtin_registry()
    return registry.create(name, config)


def list_builtin_tools() -> List[BuiltinDef]:
    """
    List all builtin tool definitions.

    Returns:
        List of tool definitions
    """
    registry = get_builtin_registry()
    return list(registry.all().values())
