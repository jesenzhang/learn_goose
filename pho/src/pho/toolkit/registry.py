"""
Unified Tool Registry - Central registration and management of tools.

Supports multiple registration methods:
1. Decorator-based (@register_tool)
2. Skill-based (SKILL.md + scripts/)
3. MCP-based (from MCP extensions)
"""

import inspect
import logging
from typing import Dict, Any, Optional, Callable, List, Union, Type
from dataclasses import dataclass, field
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class ToolType(str, Enum):
    """Types of tool registration"""
    DECORATOR = "decorator"     # Registered via @register_tool decorator
    SKILL = "skill"             # Loaded from skill directory (SKILL.md)
    MCP = "mcp"                 # From MCP extension
    BUILTIN = "builtin"         # Built-in tool


@dataclass
class ToolMetadata:
    """Metadata for a registered tool"""
    name: str
    description: str
    function: Callable
    tool_type: ToolType
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: Optional[str] = None
    enabled: bool = True
    source: Optional[str] = None  # e.g., skill name, MCP server name
    permission: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None


class ToolRegistry:
    """
    Unified registry for tool management.

    Supports decorator, skill, and MCP-based tool registration.
    """

    def __init__(self):
        """Initialize the tool registry"""
        self._tools: Dict[str, ToolMetadata] = {}
        self._by_type: Dict[ToolType, Dict[str, ToolMetadata]] = {
            t: {} for t in ToolType
        }
        self._by_category: Dict[str, Dict[str, ToolMetadata]] = {}
        self._decorators: List[Callable] = []

    # ========================================================================
    # Registration Methods
    # ========================================================================

    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        tool_type: ToolType = ToolType.DECORATOR,
        category: Optional[str] = None,
        source: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        **metadata
    ) -> None:
        """
        Register a tool.

        Args:
            name: Unique tool name
            func: Tool function (sync or async)
            description: Tool description
            tool_type: Type of tool registration
            category: Tool category for organization
            source: Source of the tool (skill name, MCP server, etc.)
            schema: JSON schema for parameters
            **metadata: Additional metadata
        """
        # Extract parameter schema if not provided
        if schema is None:
            schema = self._extract_schema(func)

        metadata_obj = ToolMetadata(
            name=name,
            description=description,
            function=func,
            tool_type=tool_type,
            parameters=schema.get("properties", {}),
            category=category,
            source=source,
            schema=schema
        )

        self._tools[name] = metadata_obj
        self._by_type[tool_type][name] = metadata_obj

        if category:
            if category not in self._by_category:
                self._by_category[category] = {}
            self._by_category[category][name] = metadata_obj

        logger.debug(f"Registered tool: {name} (type: {tool_type.value})")

    def register_decorator(
        self,
        name: str,
        description: str = "",
        category: Optional[str] = None,
        **kwargs
    ) -> Callable:
        """
        Decorator for tool registration.

        Usage:
            @registry.register_decorator("my_tool", description="Does something")
            def my_tool(arg1: str, arg2: int) -> str:
                return f"Result: {arg1} {arg2}"
        """
        def decorator(func: Callable) -> Callable:
            self.register(
                name=name,
                func=func,
                description=description,
                tool_type=ToolType.DECORATOR,
                category=category,
                **kwargs
            )
            return func
        return decorator

    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name not in self._tools:
            return False

        metadata = self._tools[name]

        # Remove from all indexes
        del self._tools[name]
        del self._by_type[metadata.tool_type][name]

        if metadata.category and metadata.category in self._by_category:
            self._by_category[metadata.category].pop(name, None)

        logger.debug(f"Unregistered tool: {name}")
        return True

    # ========================================================================
    # Query Methods
    # ========================================================================

    def get(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name"""
        return self._tools.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """Get tool function by name"""
        metadata = self.get(name)
        return metadata.function if metadata else None

    def list_all(self) -> Dict[str, ToolMetadata]:
        """List all registered tools"""
        return self._tools.copy()

    def list_by_type(self, tool_type: ToolType) -> Dict[str, ToolMetadata]:
        """List tools by type"""
        return self._by_type[tool_type].copy()

    def list_by_category(self, category: str) -> Dict[str, ToolMetadata]:
        """List tools by category"""
        return self._by_category.get(category, {}).copy()

    def list_enabled(self) -> Dict[str, ToolMetadata]:
        """List only enabled tools"""
        return {
            name: meta for name, meta in self._tools.items()
            if meta.enabled
        }

    def list_categories(self) -> List[str]:
        """List all categories"""
        return list(self._by_category.keys())

    # ========================================================================
    # Tool Execution
    # ========================================================================

    async def execute(
        self,
        name: str,
        **kwargs
    ) -> Any:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found or disabled
        """
        metadata = self.get(name)

        if not metadata:
            raise ValueError(f"Tool not found: {name}")

        if not metadata.enabled:
            raise ValueError(f"Tool is disabled: {name}")

        func = metadata.function

        # Execute sync or async
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            # Run sync function in executor to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, **kwargs)

    # ========================================================================
    # Tool Schema Generation
    # ========================================================================

    def _extract_schema(self, func: Callable) -> Dict[str, Any]:
        """Extract JSON schema from function signature"""
        sig = inspect.signature(func)
        parameters = {}

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_info = {
                "type": "string",
                "description": param_name
            }

            # Try to get type annotation
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = self._type_to_string(param.annotation)

            # Check for default value
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default

            parameters[param_name] = param_info

        return {
            "type": "object",
            "properties": parameters,
            "required": [
                p for p in parameters
                if sig.parameters[p].default == inspect.Parameter.empty
                and p not in ("self", "cls")
            ]
        }

    def _type_to_string(self, type_hint: type) -> str:
        """Convert type annotation to string"""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        return type_map.get(type_hint, "string")

    # ========================================================================
    # OpenAI Function Call Format
    # ========================================================================

    def to_openai_functions(self) -> List[Dict[str, Any]]:
        """
        Export tools as OpenAI function-calling format.

        Returns:
            List of function definitions
        """
        functions = []

        for metadata in self.list_enabled().values():
            func_def = {
                "name": metadata.name,
                "description": metadata.description,
                "parameters": metadata.schema or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            functions.append(func_def)

        return functions

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_tools": len(self._tools),
            "by_type": {
                t.value: len(tools)
                for t, tools in self._by_type.items()
            },
            "by_category": {
                cat: len(tools)
                for cat, tools in self._by_category.items()
            },
            "enabled": len(self.list_enabled()),
            "disabled": len(self._tools) - len(self.list_enabled()),
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self)} tools)"


# ========================================================================
# Global Registry Instance
# ========================================================================

_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """Get the global tool registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(
    name: str,
    description: str = "",
    category: Optional[str] = None,
    **kwargs
) -> Callable:
    """
    Global decorator for tool registration.

    Usage:
        @register_tool("my_tool", description="Does something")
        def my_tool(arg1: str) -> str:
            return arg1
    """
    return get_global_registry().register_decorator(
        name=name,
        description=description,
        category=category,
        **kwargs
    )


__all__ = [
    "ToolType",
    "ToolMetadata",
    "ToolRegistry",
    "get_global_registry",
    "register_tool",
]
