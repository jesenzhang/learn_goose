"""
Registry system for Pho framework.

Provides generic registry functionality for components, tools, skills, etc.
"""

import logging
from typing import Dict, TypeVar, Generic, List, Optional, Any, Type
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("pho.registry")

# ==========================================
# 1. Base Data Structures
# ==========================================

B = TypeVar("B")  # Body
M = TypeVar("M")  # Meta


class RegistryEntry(BaseModel, Generic[B, M]):
    """A registry entry containing a body and metadata."""
    id: str
    body: B
    meta: M

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BaseRegistry(Generic[B, M]):
    """Generic registry for storing and retrieving entries."""

    def __init__(self, name: str):
        self._name = name
        self._entries: Dict[str, RegistryEntry[B, M]] = {}

    def register(self, entry: RegistryEntry[B, M]):
        """Register an entry in the registry."""
        if not entry:
            logger.warning("Empty entry cannot be registered.")
            return

        if entry.id in self._entries:
            logger.warning(f"Overwriting {self._name}: {entry.id}")
        self._entries[entry.id] = entry
        logger.debug(f"Registered {self._name}: {entry.id}")

    def get_entry(self, key: str) -> Optional[RegistryEntry[B, M]]:
        """Get the full entry for a key."""
        e = self._entries.get(key)
        return e if e else None

    def get(self, key: str) -> Optional[B]:
        """Get the body for a key."""
        e = self._entries.get(key)
        return e.body if e else None

    def get_body(self, key: str) -> Optional[B]:
        """Get the body for a key."""
        e = self._entries.get(key)
        return e.body if e else None

    def get_meta(self, key: str) -> Optional[M]:
        """Get the metadata for a key."""
        e = self._entries.get(key)
        return e.meta if e else None

    def list_entries(self) -> List[RegistryEntry[B, M]]:
        """List all entries."""
        return list(self._entries.values())

    def list_meta(self) -> List[M]:
        """List all metadata."""
        return [e.meta for e in self._entries.values()]

    def list_body(self) -> List[B]:
        """List all bodies."""
        return [e.body for e in self._entries.values()]

    def clear(self):
        """Clear all entries."""
        self._entries.clear()


# ==========================================
# 2. System Registry (Singleton)
# ==========================================

class SystemRegistry:
    """
    System registry singleton.

    Features:
    1. Global singleton: same instance regardless of how many times instantiated.
    2. Dynamic attributes: registry.knowledge auto-creates registry.
    3. Explicit registration: register_domain for custom behavior.
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """Singleton guard - return same instance if exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the system registry (only once)."""
        if self._initialized:
            return

        self._domains: Dict[str, BaseRegistry] = {}
        self._initialized = True
        logger.info("SystemRegistry initialized (Singleton).")

    def register_domain(self, name: str, registry_instance: BaseRegistry):
        """Register a new domain registry."""
        if name in self._domains:
            logger.warning(f"Domain '{name}' is being overwritten.")
        self._domains[name] = registry_instance
        logger.info(f"Domain registered: system.{name}")

    def __getattr__(self, name: str) -> BaseRegistry:
        """
        Attribute access proxy.

        When you call registry.knowledge:
        1. If exists, return it.
        2. If not, auto-create a default BaseRegistry.
        """
        # Avoid infinite recursion for internal attributes
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        if name not in self._domains:
            logger.info(f"Auto-initializing domain registry: {name}")
            self._domains[name] = BaseRegistry(name)

        return self._domains[name]

    def __dir__(self):
        """Help IDE and dir() discover dynamic attributes."""
        return list(self.__dict__.keys()) + list(self._domains.keys())


# Global singleton instance
sys_registry = SystemRegistry()


__all__ = [
    "RegistryEntry",
    "BaseRegistry",
    "SystemRegistry",
    "sys_registry",
]
