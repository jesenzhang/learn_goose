"""
System Store registry and plugin loader.
"""

from __future__ import annotations

import importlib
import logging
from importlib import metadata
from typing import Dict, Optional, Type

from .base import Store, StoreConfig, StoreType

logger = logging.getLogger(__name__)


class StoreRegistry:
    def __init__(self) -> None:
        self._stores: Dict[StoreType, Type[Store]] = {}

    def register(self, store_type: StoreType, store_cls: Type[Store]) -> None:
        self._stores[store_type] = store_cls

    def get(self, store_type: StoreType) -> Optional[Type[Store]]:
        return self._stores.get(store_type)

    def create(self, scope_id: str, config: StoreConfig) -> Store:
        if config.plugin_path:
            store_cls = load_plugin(config.plugin_path)
        else:
            store_cls = self.get(config.store_type)
        if store_cls is None:
            raise RuntimeError(f"Store not registered: {config.store_type}")
        return store_cls(scope_id, config, **(config.plugin_settings or {}))


_global_registry = StoreRegistry()


def register_store(store_type: StoreType):
    def decorator(store_cls: Type[Store]) -> Type[Store]:
        _global_registry.register(store_type, store_cls)
        return store_cls
    return decorator


def get_registry() -> StoreRegistry:
    return _global_registry


def load_entrypoints(group: str = "assistant.system_stores") -> int:
    loaded = 0
    try:
        eps = metadata.entry_points()
        candidates = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
    except Exception as e:
        logger.warning(f"Failed to load store entrypoints for group '{group}': {e}")
        return 0
    for ep in candidates:
        try:
            store_cls = ep.load()
            store_type = None
            if hasattr(store_cls, "STORE_TYPE"):
                store_type = getattr(store_cls, "STORE_TYPE")
            else:
                try:
                    store_type = StoreType(ep.name)
                except Exception:
                    store_type = None
            if store_type:
                _global_registry.register(store_type, store_cls)
                loaded += 1
                logger.info(f"Loaded store entrypoint: {ep.name} -> {store_cls}")
            else:
                logger.warning(f"Store entrypoint '{ep.name}' has no StoreType mapping")
        except Exception:
            logger.exception(f"Failed to load store entrypoint '{ep.name}'")
    return loaded


def load_plugin(path: str) -> Type[Store]:
    if ":" in path:
        module_path, class_name = path.split(":", 1)
    else:
        module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    store_cls = getattr(module, class_name, None)
    if store_cls is None:
        raise RuntimeError(f"Plugin class not found: {path}")
    return store_cls


load_entrypoints()
