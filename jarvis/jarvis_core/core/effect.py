"""
Effect System - Side-effect declarations.

Effects describe WHAT to do, by not HOW to do it.
The Executor decides WHEN and HOW to execute effects.

This separation enables:
- Event sourcing (effects become events)
- Replay (effects can be re-executed)
- Testing (effects can be mocked)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
import uuid


class EffectType(str, Enum):
    """Standard effect types."""
    # LLM Effects
    LLM_GENERATE = "llm_generate"
    LLM_STREAM = "llm_stream"

    # Tool Effects
    TOOL_CALL = "tool_call"
    TOOL_BATCH = "tool_batch"

    # State Effects
    SAVE_STATE = "save_state"
    LOAD_STATE = "load_state"

    # Storage Effects
    STORE_ARTIFACT = "store_artifact"
    LOAD_ARTIFACT = "load_artifact"

    # Human Effects
    REQUEST_APPROVAL = "request_approval"

    # Skill Effects
    ACTIVATE_SKILL = "activate_skill"
    EXIT_SKILL = "exit_skill"

    # Custom Effects
    CUSTOM = "custom"


@dataclass
class Effect:
    """
    Declaration of a side effect.

    Effects are produced by Agent.reduce() and describe
    what external actions should be taken.

    Key design:
    - Effects are data-only (no callbacks)
    - Effects are serializable
    - Effects have retry/timeout policies
    """
    # Required fields (no defaults)
    effect_type: EffectType  # Renamed from 'type' to avoid keyword conflict

    # Optional fields with defaults
    effect_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    payload: Dict[str, Any] = field(default_factory=dict)

    # Execution policy
    retry: int = 3
    timeout: float = 30.0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "effect_id": self.effect_id,
            "type": self.effect_type.value,
            "payload": self.payload,
            "retry": self.retry,
            "timeout": self.timeout,
            "metadata": self.metadata,
        }


# =========================================================================
# Effect Factories
# =========================================================================

def llm_generate_effect(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: Optional[float] = None,
    **kwargs,
) -> Effect:
    """Create an LLM generate effect."""
    return Effect(
        effect_type=EffectType.LLM_GENERATE,
        payload={
            "messages": messages,
            "tools": tools or [],
            **kwargs,
        },
        metadata={"temperature": temperature} if temperature else {},
    )


def llm_stream_effect(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Effect:
    """Create an LLM stream effect."""
    return Effect(
        effect_type=EffectType.LLM_STREAM,
        payload={
            "messages": messages,
            "tools": tools or [],
            **kwargs,
        },
    )


def tool_call_effect(
    tool_name: str,
    tool_args: Dict[str, Any],
    timeout: float = 30.0,
) -> Effect:
    """Create a tool call effect."""
    return Effect(
        effect_type=EffectType.TOOL_CALL,
        payload={
            "tool_name": tool_name,
            "tool_args": tool_args,
        },
        timeout=timeout,
    )


def tool_batch_effect(
    tool_calls: List[Dict[str, Any]],
    timeout: float = 30.0,
) -> Effect:
    """Create a batch tool call effect."""
    return Effect(
        effect_type=EffectType.TOOL_BATCH,
        payload={
            "tool_calls": tool_calls,
        },
        timeout=timeout,
    )


def save_state_effect(
    state: Dict[str, Any],
    session_id: str,
) -> Effect:
    """Create a save state effect."""
    return Effect(
        effect_type=EffectType.SAVE_STATE,
        payload={
            "state": state,
            "session_id": session_id,
        },
    )


def request_approval_effect(
    tool_name: str,
    tool_args: Dict[str, Any],
    reason: Optional[str] = None,
) -> Effect:
    """Create a request approval effect."""
    return Effect(
        effect_type=EffectType.REQUEST_APPROVAL,
        payload={
            "tool_name": tool_name,
            "tool_args": tool_args,
            "reason": reason or f"Execute tool: {tool_name}",
        },
    )


def activate_skill_effect(
    skill_name: str,
) -> Effect:
    """Create an activate skill effect."""
    return Effect(
        effect_type=EffectType.ACTIVATE_SKILL,
        payload={
            "skill_name": skill_name,
        },
    )


def exit_skill_effect() -> Effect:
    """Create an exit skill effect."""
    return Effect(
        effect_type=EffectType.EXIT_SKILL,
        payload={},
    )


def custom_effect(
    effect_type: str,
    payload: Dict[str, Any],
    **kwargs,
) -> Effect:
    """Create a custom effect."""
    return Effect(
        effect_type=EffectType.CUSTOM,
        payload={
            "effect_type": effect_type,
            "data": payload,
            **kwargs,
        },
    )
