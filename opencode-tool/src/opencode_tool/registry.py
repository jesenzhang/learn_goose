"""
Tool registry for managing and retrieving tools.

This module provides a central registry for all tools, allowing
dynamic tool discovery and initialization.
"""

from typing import Any, Dict, List, Optional, Set, Type

from .tool import Tool, InvalidTool


class ToolRegistry:
    """
    Central registry for all tools.

    The registry maintains a collection of tool classes and
    provides methods for registering, retrieving, and instantiating tools.
    """

    _instance: Optional["ToolRegistry"] = None

    def __new__(cls) -> "ToolRegistry":
        """Singleton pattern for registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, Type[Tool]] = {}
            cls._instance._custom_tools: List[Type[Tool]] = []
        return cls._instance

    def register(self, tool_class: Type[Tool]) -> None:
        """
        Register a tool class.

        Args:
            tool_class: The Tool subclass to register.
        """
        self._tools[tool_class.name] = tool_class

    def register_custom(self, tool_class: Type[Tool]) -> None:
        """
        Register a custom tool class.

        Custom tools are tracked separately for filtering purposes.

        Args:
            tool_class: The Tool subclass to register as custom.
        """
        self._custom_tools.append(tool_class)
        self.register(tool_class)

    def get(self, name: str) -> Type[Tool]:
        """
        Get a tool class by name.

        Args:
            name: The tool name.

        Returns:
            The Tool subclass.

        Raises:
            KeyError: If tool not found.
        """
        if name not in self._tools:
            return InvalidTool
        return self._tools[name]

    def get_instance(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tool:
        """
        Get an instance of a tool.

        Args:
            name: The tool name.
            config: Optional configuration for the tool.

        Returns:
            An instance of the Tool.
        """
        tool_class = self.get(name)
        return tool_class(config)

    def all(self) -> List[Type[Tool]]:
        """
        Get all registered tool classes.

        Returns:
            List of all Tool subclasses.
        """
        return list(self._tools.values())

    def all_custom(self) -> List[Type[Tool]]:
        """
        Get all custom tool classes.

        Returns:
            List of custom Tool subclasses.
        """
        return self._custom_tools.copy()

    def ids(self) -> List[str]:
        """
        Get all tool IDs (names).

        Returns:
            List of tool names.
        """
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

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._custom_tools.clear()


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.

    Returns:
        The singleton ToolRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool_class: Type[Tool], custom: bool = False) -> None:
    """
    Register a tool with the global registry.

    Args:
        tool_class: The Tool subclass to register.
        custom: Whether this is a custom user-provided tool.
    """
    registry = get_registry()
    if custom:
        registry.register_custom(tool_class)
    else:
        registry.register(tool_class)


def get_tool(name: str, config: Optional[Dict[str, Any]] = None) -> Tool:
    """
    Get an instance of a tool by name.

    Args:
        name: The tool name.
        config: Optional configuration for the tool.

    Returns:
        An instance of the Tool.
    """
    registry = get_registry()
    return registry.get_instance(name, config)


def get_all_tools() -> List[Type[Tool]]:
    """
    Get all registered tool classes.

    Returns:
        List of all Tool subclasses.
    """
    registry = get_registry()
    return registry.all()


def get_tool_ids() -> List[str]:
    """
    Get all tool IDs.

    Returns:
        List of tool names.
    """
    registry = get_registry()
    return registry.ids()
