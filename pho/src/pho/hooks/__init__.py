"""
Hook System - Enhanced version
"""

from .base import (
    AgentHook,
    HookResult,
    HookContext,
    HookAction,
    HookConfig,
)

from .manager import (
    HookManager,
    HookRegistry,
    HookConfigLoader,
    register_hook,
)

from .faq_hook import FAQHook
from .security_hooks import SensitiveWordHook, PromptInjectionHook
from .utility_hooks import RequestLoggerHook, InputValidatorHook, StatisticsCollectorHook

__all__ = [
    # Base
    "AgentHook",
    "HookResult",
    "HookContext",
    "HookAction",
    "HookConfig",

    # Manager
    "HookManager",
    "HookRegistry",
    "HookConfigLoader",
    "register_hook",

    # Built-in Hooks
    "FAQHook",
    "SensitiveWordHook",
    "PromptInjectionHook",
    "RequestLoggerHook",
    "InputValidatorHook",
    "StatisticsCollectorHook",
]
