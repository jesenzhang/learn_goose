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

from .tool import ToolSourceType, ToolDefinition,FunctionTool,BaseTool
logger = logging.getLogger(__name__)




class ToolRegistry:
    """
    Unified registry for tool management.

    Supports decorator, skill, and MCP-based tool registration.
    """

    def __init__(self):
        """Initialize the tool registry"""
        self._tools: Dict[str, ToolDefinition] = {}
        self._by_type: Dict[ToolSourceType, Dict[str, ToolDefinition]] = {
            t: {} for t in ToolSourceType
        }
        self._by_category: Dict[str, Dict[str, ToolDefinition]] = {}
        self._decorators: List[Callable] = []

    # ========================================================================
    # Registration Methods
    # ========================================================================

    # ========================================================================
    # Registration Methods
    # ========================================================================

    def register_tool_class(
        self,
        tool_class: Type[BaseTool],
        source_type: ToolSourceType = ToolSourceType.BUILTIN,
        category: Optional[str] = None,
        **metadata
    ) -> None:
        """
        Register a tool class.

        Args:
            tool_class: BaseTool subclass
            source_type: Type of registration
            category: Tool category
            source: Source identifier
            **metadata: Additional metadata
        """
        # Create tool instance to get metadata
        tool_instance = tool_class()
        tool_name = tool_instance.name
        tool_desc = tool_instance.description

        metadata_obj = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            source_type=source_type,
            function=tool_instance.run,  # Use the run method
            category=category or tool_instance.category,
            schema=tool_instance.schema,
            parameters=tool_instance.schema.get("properties", {}),
            **metadata
        )

        self._register_metadata(metadata_obj)

    def register_function(
        self,
        name: str,
        func: Callable,
        description: str = "",
        source_type: ToolSourceType = ToolSourceType.DECORATOR,
        category: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        **metadata
    ) -> None:
        """
        Register a function as a tool.

        Args:
            name: Tool name
            func: Function to register
            description: Tool description
            source_type: Type of registration
            category: Tool category
            source: Source identifier
            schema: Parameter schema
            **metadata: Additional metadata
        """
        # Extract schema if not provided
        if schema is None:
            schema = self._extract_function_schema(func)

        # 2. 【核心修改】不再只存 Metadata，而是创建一个 FunctionTool 实例
        # 这样所有的工具（无论是类写的，还是函数写的）在系统里都是 BaseTool 对象！
        tool_instance = FunctionTool(
            func=func,
            schema=schema,
            name=name,
            description=description,
            **metadata
        )
        
        metadata_obj = ToolDefinition(
            name=name,
            description=description or getattr(func, "__doc__", "") or "",
            source_type=source_type,
            function=tool_instance.run,
            category=category,
            schema=schema,
            parameters=schema.get("properties", {}),
            **metadata
        )

        self._register_metadata(metadata_obj)

    def _register_metadata(self, metadata: ToolDefinition) -> None:
        """Internal method to register metadata"""
        self._tools[metadata.name] = metadata
        self._by_type[metadata.source_type][metadata.name] = metadata

        if metadata.category:
            if metadata.category not in self._by_category:
                self._by_category[metadata.category] = {}
            self._by_category[metadata.category][metadata.name] = metadata

        logger.debug(f"Registered tool: {metadata.name} (type: {metadata.source_type.value})")

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
            self.register_function(
                name=name,
                func=func,
                description=description,
                source_type=ToolSourceType.DECORATOR,
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
        del self._by_type[metadata.source_type][name]

        if metadata.category and metadata.category in self._by_category:
            self._by_category[metadata.category].pop(name, None)

        logger.debug(f"Unregistered tool: {name}")
        return True

    # ========================================================================
    # Query Methods
    # ========================================================================
    def ids(self):
        """Get all registered tool names"""
        return list(self._tools.keys())

    def has(self, name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            name: The tool name.

        Returns:
            True if tool is registered, False otherwise.
        """
        return name in self._tools
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool metadata by name"""
        return self._tools.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """Get tool function by name"""
        metadata = self.get(name)
        return metadata.function if metadata else None

    def list_all(self) -> Dict[str, ToolDefinition]:
        """List all registered tools"""
        return self._tools.copy()

    def list_by_type(self, tool_type: ToolSourceType) -> Dict[str, ToolDefinition]:
        """List tools by type"""
        return self._by_type[tool_type].copy()

    def list_by_category(self, category: str) -> Dict[str, ToolDefinition]:
        """List tools by category"""
        return self._by_category.get(category, {}).copy()

    def list_enabled(self) -> Dict[str, ToolDefinition]:
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

    def _extract_function_schema(self, func: Callable) -> Dict[str, Any]:
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


# # ========================================================================
# # Global Registry Instance
# # ========================================================================

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


def register_tool_class(
    tool_class: Type[BaseTool],
    source_type: ToolSourceType = ToolSourceType.BUILTIN,
    category: Optional[str] = None,
    **kwargs
) -> None:
    """
    Register a tool class globally.

    Args:
        tool_class: BaseTool subclass
        source_type: Type of registration
        category: Tool category
        **kwargs: Additional metadata
    """
    get_global_registry().register_tool_class(
        tool_class=tool_class,
        source_type=source_type,
        category=category,
        **kwargs
    )

tool_registry = get_global_registry()
