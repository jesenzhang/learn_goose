"""Core agent modules."""

import os

from ..events import EventType, Event
from .state import AgentState, AgentStatus

if os.getenv("ASSISTANT_AGENT_V2", "false").lower() == "true":
    from .V2.agent import MicroAgentV2 as MicroAgent
else:
    from .agent import MicroAgent

__all__ = [
    "EventType",
    "Event",
    "AgentState",
    "AgentStatus",
    "MicroAgent",
]
