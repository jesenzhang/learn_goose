"""
Configuration Loader Module
"""

import os
import logging
from typing import Dict, List, Set, Any, Type,Optional
from pathlib import Path
import yaml
from pydantic import ValidationError

from .models import AppConfig
# Import directly from single source of truth
from ..intent.models import IntentDefinition, SlotSchema
# Import module configuration classes
from ..truncation import TruncationConfig as TruncationModuleConfig
from ..chatrecall import ChatRecallConfig as ChatRecallModuleConfig
from ..memory import MemoryConfig as MemoryModuleConfig
from ..store import StoreConfig as StoreModuleConfig

logger = logging.getLogger(__name__)

# Mapping YAML string types to Python classes
TYPE_MAP: Dict[str, Type] = {
    'str': str, 'string': str,
    'int': int, 'integer': int,
    'float': float, 'number': float,
    'bool': bool, 'boolean': bool,
    'list': list, 'array': list,
    'dict': dict, 'object': dict,
}

class ConfigLoader:
    def __init__(self, config_path: str = "agent_config.yaml"):
        self.config_path = config_path

        # 1. Load Raw YAML (Preserved for flexible execution configs)
        self.raw_data: Dict[str, Any] = self._load_raw_yaml()

        # 2. Validate Core Config (Pydantic)
        self.config: AppConfig = self._validate_core_config()

        logger.info(f"Configuration loaded from {self.config_path}")

    def _load_raw_yaml(self) -> Dict[str, Any]:
        path = Path(self.config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.error(f"YAML error: {e}")
            raise

    def _validate_core_config(self) -> AppConfig:
        try:
            return AppConfig(**self.raw_data)
        except ValidationError as e:
            logger.error(f"Config validation error: {e}")
            raise

    # =========================================================================
    # Factory: Dict (Config) -> Object (Runtime Model)
    # =========================================================================
    def get_intent_definitions(self) -> List[IntentDefinition]:
        """
        Transform raw config dicts into Runtime IntentDefinitions.
        """
        definitions = []

        # self.config.intents is Dict[str, Any]
        for name, data in self.config.intents.items():
            try:
                # 1. Parse Slots
                slots = []
                slots_data = data.get("slots", {})

                for slot_name, slot_def in slots_data.items():
                    # Map string type (e.g. "int") to Python type (int)
                    type_str = slot_def.get("type", "str")
                    py_type = TYPE_MAP.get(type_str.lower(), str)

                    slots.append(SlotSchema(
                        name=slot_name,
                        description=slot_def.get("description", ""),
                        required=slot_def.get("required", False),
                        data_type=py_type,
                        default=slot_def.get("default", None),
                        options=slot_def.get("options", None)
                    ))

                # 2. Create Intent Definition
                definitions.append(IntentDefinition(
                    name=name,
                    label=data.get("label", name),
                    description=data.get("description", f"Intent: {name}"),
                    slots=slots
                ))
            except Exception as e:
                logger.error(f"Failed to parse intent definition for '{name}': {e}")
                continue

        return definitions

    # --- Accessors ---
    @property
    def system(self): return self.config.system
    @property
    def provider(self): return self.config.provider
    @property
    def agent(self): return self.config.agent
    @property
    def security(self): return self.config.security

    @property
    def database(self): return self.config.database

    @property
    def skills_directory(self) -> str:
        return self.config.skills_directory

    @property
    def sensitive_tools(self) -> Set[str]:
        """Get set of sensitive tool names."""
        return set(self.config.security.sensitive_tools)

    @property
    def skills_config(self) -> Dict[str, Dict[str, Any]]:
        """Get skills configuration dict."""
        return self.config.skills_config.root

    @property
    def truncation(self) -> TruncationModuleConfig:
        """Get truncation configuration as dataclass."""
        config = self.config.truncation
        return TruncationModuleConfig(
            enabled=config.enabled,
            threshold=config.threshold,
            auto_compact=config.auto_compact,
            max_messages_before_compact=config.max_messages_before_compact,
            keep_recent_messages=config.keep_recent_messages,
            check_interval=config.check_interval,
        )

    @property
    def chatrecall(self) -> ChatRecallModuleConfig:
        """Get chatrecall configuration as dataclass."""
        config = self.config.chatrecall
        mem_cfg = getattr(self.config, "memory", None)
        if mem_cfg is not None and getattr(mem_cfg, "chatrecall", None) is not None:
            config = mem_cfg.chatrecall
        return ChatRecallModuleConfig(
            enabled=config.enabled,
            max_results=config.max_results,
            max_session_messages=config.max_session_messages,
            min_similarity=config.min_similarity,
            query_expand_max_msgs=config.query_expand_max_msgs,
            query_max_chars=config.query_max_chars,
            query_rewrite_enabled=config.query_rewrite_enabled,
            query_rewrite_max_msgs=config.query_rewrite_max_msgs,
            query_rewrite_max_chars=config.query_rewrite_max_chars,
            query_rewrite_prompt=config.query_rewrite_prompt,
            use_semantic=config.use_semantic,
            semantic_top_k=config.semantic_top_k,
            use_rerank=config.use_rerank,
            rerank_top_k=config.rerank_top_k,
            rerank_threshold=config.rerank_threshold,
            session_memory_enabled=config.session_memory_enabled,
            session_memory_use_llm=config.session_memory_use_llm,
            session_summary_max_chars=config.session_summary_max_chars,
            session_facts_max_items=config.session_facts_max_items,
            session_entities_max_items=config.session_entities_max_items,
            session_topics_max_items=config.session_topics_max_items,
        )

    @property
    def memory(self) -> MemoryModuleConfig:
        """Get memory configuration as dataclass."""
        mem_cfg = self.config.memory
        profiles, routing, default_store = self._build_memory_store_profiles(mem_cfg)
        return MemoryModuleConfig(
            enabled=getattr(mem_cfg, "enabled", True),
            store_factory=None,
            store_profiles=profiles,
            store_routing=routing,
            default_store=default_store,
        )

    @property
    def memory_store(self) -> StoreModuleConfig:
        """Get store configuration for memory module."""
        mem_cfg = self.config.memory
        profiles, _routing, default_store = self._build_memory_store_profiles(mem_cfg)
        return profiles.get(default_store, StoreModuleConfig())

    def _build_memory_store_profiles(self, mem_cfg) -> tuple[Dict[str, StoreModuleConfig], Dict[str, str], str]:
        stores_cfg = getattr(mem_cfg, "stores", None)
        routing_cfg = getattr(mem_cfg, "routing", None)
        legacy_artifact_cfg = self.raw_data.get("artifact_manager") if isinstance(self.raw_data, dict) else None
        profiles: Dict[str, StoreModuleConfig] = {}
        routing: Dict[str, str] = {}

        if stores_cfg:
            stores_data = stores_cfg.model_dump() if hasattr(stores_cfg, "model_dump") else dict(stores_cfg)
            for key, value in stores_data.items():
                store_data = value.model_dump() if hasattr(value, "model_dump") else dict(value)
                profiles[key] = StoreModuleConfig(
                    store_type=store_data.get("store_type", key),
                    enabled=store_data.get("enabled", True),
                    base_dir=store_data.get("base_dir", "memories"),
                    db_path=store_data.get("db_path", "memory_store.db"),
                    memory_threshold=store_data.get("memory_threshold", 10 * 1024),
                    file_threshold=store_data.get("file_threshold", 100 * 1024),
                    compression=store_data.get("compression", True),
                    max_items=store_data.get("max_items", 50),
                    max_size_bytes=store_data.get("max_size_bytes", 50 * 1024 * 1024),
                    ttl=store_data.get("ttl", 86400),
                    cleanup_interval=store_data.get("cleanup_interval", 3600),
                    plugin_path=store_data.get("plugin_path"),
                    plugin_settings=store_data.get("plugin_settings", {}),
                )
        else:
            store_cfg = getattr(mem_cfg, "store", None)
            if legacy_artifact_cfg:
                store_cfg = legacy_artifact_cfg
            if store_cfg is None:
                store_cfg = {}
            store_data = store_cfg.model_dump() if hasattr(store_cfg, "model_dump") else dict(store_cfg)
            profiles["memory"] = StoreModuleConfig(
                store_type=store_data.get("store_type", "memory"),
                enabled=store_data.get("enabled", True),
                base_dir=store_data.get("base_dir", "memories"),
                db_path=store_data.get("db_path", "memory_store.db"),
                memory_threshold=store_data.get("memory_threshold", 10 * 1024),
                file_threshold=store_data.get("file_threshold", 100 * 1024),
                compression=store_data.get("compression", True),
                max_items=store_data.get("max_items", 50),
                max_size_bytes=store_data.get("max_size_bytes", 50 * 1024 * 1024),
                ttl=store_data.get("ttl", 86400),
                cleanup_interval=store_data.get("cleanup_interval", 3600),
                plugin_path=store_data.get("plugin_path"),
                plugin_settings=store_data.get("plugin_settings", {}),
            )

        if routing_cfg:
            routing = routing_cfg.model_dump() if hasattr(routing_cfg, "model_dump") else dict(routing_cfg)

        default_store = "memory"
        if profiles:
            default_store = next(iter(profiles.keys()))
        return profiles, routing, default_store

    @property
    def hooks(self) -> Dict[str, Any]:
        """Get hooks configuration dict."""
        return self.config.hooks_config.root

    @property
    def events(self):
        """Get events configuration."""
        return self.config.events

    def is_sensitive(self, tool_name: str) -> bool:
        return tool_name in self.config.security.sensitive_tools

    def get_api_key(self) -> str:
        if self.config.model.api_key:
            return self.config.model.api_key
        key = os.getenv(self.config.model.api_key_env)
        if not key:
            # Only warn here, raise runtime error later if needed
            logger.warning(f"API Key not found in {self.config.model.api_key_env}")
            return ""
        return key
