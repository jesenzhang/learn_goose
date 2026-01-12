"""
Intent Recognition Module - LLM-based intent recognition and handling.

Provides:
- Intent and slot definitions
- Intent recognition engine
- Configurable execution strategies
- Intent handler registration and routing
- Multi-intent support
- Session state management
"""

from .models import (
    SlotSchema,
    IntentDefinition,
    IntentResult,
    MultiIntentResult,
    IntentSession,
    IntentRecognitionConfig,
)
from .recognizer import IntentRecognizer, PromptBuilder
from .handler import IntentHandler, IntentRouter, create_handler_from_config
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
from .config_loader import IntentConfigLoader

__all__ = [
    # Models
    "SlotSchema",
    "IntentDefinition",
    "IntentResult",
    "MultiIntentResult",
    "IntentSession",
    "IntentRecognitionConfig",

    # Recognizer
    "IntentRecognizer",
    "PromptBuilder",

    # Handler
    "IntentHandler",
    "IntentRouter",
    "create_handler_from_config",

    # Strategy
    "ExecutionConfig",
    "ExecutionMode",
    "TerminationAction",
    "ToolCall",
    "IntentExecutor",
    "llm_mode",
    "direct_mode",
    "skill_mode",
    "chain_mode",

    # Config Loader
    "IntentConfigLoader",
]
