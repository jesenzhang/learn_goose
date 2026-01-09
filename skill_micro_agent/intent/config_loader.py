"""
Intent Configuration Loader - Load intent execution strategies from YAML.

Extends the YAML configuration to support execution mode definitions.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from .strategy import (
    ExecutionConfig,
    ExecutionMode,
    TerminationAction,
    ToolCall,
    IntentExecutor,
    llm_mode,
    direct_mode,
    skill_mode,
    chain_mode,
)

logger = logging.getLogger(__name__)


class IntentConfigLoader:
    """
    Loads intent execution configs from YAML structure.

    Example YAML:
    ```yaml
    intents:
      recommend_exhibits:
        description: "推荐文物藏品"
        slots:
          keywords: {type: str, required: true}
        execution:
          mode: "skill"
          skill_name: "asset-search"
          on_complete: "continue"

      get_time:
        description: "获取当前时间"
        execution:
          mode: "direct"
          handler: "tools.get_current_time"
          on_complete: "stop"
    ```
    """

    def __init__(self, handler_registry: Optional[Dict[str, Callable]] = None):
        """
        Initialize loader.

        Args:
            handler_registry: Map of handler names to functions (for DIRECT mode)
        """
        self.handler_registry = handler_registry or {}

    def load_from_config(
        self,
        config_dict: Dict[str, Any],
        executor: IntentExecutor
    ) -> None:
        """
        Load all intent execution configs from YAML structure.

        Args:
            config_dict: Parsed YAML configuration
            executor: IntentExecutor to register configs with
        """
        intents = config_dict.get("intents", {})

        for intent_name, intent_def in intents.items():
            exec_def = intent_def.get("execution")

            if not exec_def:
                # Default to LLM mode
                continue

            try:
                config = self._parse_execution_config(intent_name, exec_def)
                if config:
                    executor.register(intent_name, config)
            except Exception as e:
                logger.warning(f"Failed to load execution config for {intent_name}: {e}")

    def _parse_execution_config(
        self,
        intent_name: str,
        exec_def: Dict[str, Any]
    ) -> Optional[ExecutionConfig]:
        """Parse execution config from YAML definition."""
        mode_str = exec_def.get("mode", "llm").lower()
        mode = ExecutionMode(mode_str)

        if mode == ExecutionMode.LLM:
            return self._parse_llm_config(exec_def)
        elif mode == ExecutionMode.DIRECT:
            return self._parse_direct_config(exec_def)
        elif mode == ExecutionMode.SKILL:
            return self._parse_skill_config(exec_def)
        elif mode == ExecutionMode.CHAIN:
            return self._parse_chain_config(exec_def)
        elif mode == ExecutionMode.HYBRID:
            return self._parse_hybrid_config(exec_def)
        else:
            logger.warning(f"Unknown execution mode: {mode_str}")
            return None

    def _parse_llm_config(self, exec_def: Dict[str, Any]) -> ExecutionConfig:
        """Parse LLM mode config."""
        return ExecutionConfig(
            mode=ExecutionMode.LLM,
            allowed_tools=exec_def.get("allowed_tools", []),
            denied_tools=exec_def.get("denied_tools", []),
            on_complete=self._parse_termination(exec_def.get("on_complete", "continue"))
        )

    def _parse_direct_config(self, exec_def: Dict[str, Any]) -> ExecutionConfig:
        """Parse DIRECT mode config."""
        handler_name = exec_def.get("handler")
        if not handler_name:
            raise ValueError("DIRECT mode requires 'handler'")

        handler = self._resolve_handler(handler_name)
        if not handler:
            raise ValueError(f"Handler not found: {handler_name}")

        return ExecutionConfig(
            mode=ExecutionMode.DIRECT,
            handler=handler,
            response_template=exec_def.get("response_template"),
            on_complete=self._parse_termination(exec_def.get("on_complete", "stop"))
        )

    def _parse_skill_config(self, exec_def: Dict[str, Any]) -> ExecutionConfig:
        """Parse SKILL mode config."""
        skill_name = exec_def.get("skill_name")
        if not skill_name:
            raise ValueError("SKILL mode requires 'skill_name'")

        return ExecutionConfig(
            mode=ExecutionMode.SKILL,
            skill_name=skill_name,
            skill_params=exec_def.get("skill_params", {}),
            on_complete=self._parse_termination(exec_def.get("on_complete", "continue"))
        )

    def _parse_chain_config(self, exec_def: Dict[str, Any]) -> ExecutionConfig:
        """Parse CHAIN mode config."""
        chain_defs = exec_def.get("tool_chain", [])
        tool_chain = []

        for step in chain_defs:
            tool = step.get("tool")
            if not tool:
                continue

            tool_chain.append(ToolCall(
                tool=tool,
                arguments=step.get("arguments", {}),
                from_slot=step.get("from_slot"),
                output_to=step.get("output_to")
            ))

        return ExecutionConfig(
            mode=ExecutionMode.CHAIN,
            tool_chain=tool_chain,
            on_complete=self._parse_termination(exec_def.get("on_complete", "stop"))
        )

    def _parse_hybrid_config(self, exec_def: Dict[str, Any]) -> ExecutionConfig:
        """Parse HYBRID mode config (LLM + hooks)."""
        pre_hook = self._resolve_handler(exec_def.get("pre_hook"))
        post_hook = self._resolve_handler(exec_def.get("post_hook"))

        return ExecutionConfig(
            mode=ExecutionMode.HYBRID,
            allowed_tools=exec_def.get("allowed_tools", []),
            pre_hook=pre_hook,
            post_hook=post_hook,
            on_complete=self._parse_termination(exec_def.get("on_complete", "continue"))
        )

    def _parse_termination(self, value: str) -> TerminationAction:
        """Parse termination action from string."""
        if isinstance(value, TerminationAction):
            return value
        return TerminationAction(value.lower())

    def _resolve_handler(self, handler_ref: str) -> Optional[Callable]:
        """
        Resolve handler from string reference.

        Supports:
        - "module.function" format
        - Registered handler names
        """
        if not handler_ref:
            return None

        # Check registry first
        if handler_ref in self.handler_registry:
            return self.handler_registry[handler_ref]

        # Try to import from module
        if "." in handler_ref:
            try:
                module_path, func_name = handler_ref.rsplit(".", 1)
                module = __import__(module_path, fromlist=[func_name])
                return getattr(module, func_name, None)
            except (ImportError, AttributeError) as e:
                logger.warning(f"Failed to import handler {handler_ref}: {e}")

        return None

    def register_handler(self, name: str, handler: Callable) -> None:
        """Register a handler for reference in YAML."""
        self.handler_registry[name] = handler
