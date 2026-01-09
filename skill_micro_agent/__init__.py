"""
Skill MicroAgent - Event-driven LLM Agent Framework

A modular, event-driven agent system with:
- Tool execution with dependency injection
- Human-in-the-loop approval workflow
- Concurrent tool execution
- State persistence with SQLite
- Streaming responses

Usage:
    from skill_micro_agent import MicroAgent, ConfigLoader

    config = ConfigLoader("agent_config.yaml")
    agent = MicroAgent(config)
"""

__version__ = "2.0.0"

from skill_micro_agent.core.agent import MicroAgent
from skill_micro_agent.core.events import EventManager, EventType, Event
from skill_micro_agent.core.state import AgentState, AgentStatus
from skill_micro_agent.db import get_db, DatabaseManager
from skill_micro_agent.config.loader import ConfigLoader

__all__ = [
    "MicroAgent",
    "EventManager",
    "EventType",
    "Event",
    "AgentState",
    "AgentStatus",
    "get_db",
    "DatabaseManager",
    "ConfigLoader",
]
