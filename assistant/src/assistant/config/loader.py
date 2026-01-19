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
# Import directly from the single source of truth
from ..intent.models import IntentDefinition, SlotSchema

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
    def hooks(self) -> Dict[str, Any]:
        """Get hooks configuration dict."""
        return self.config.hooks_config.root

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