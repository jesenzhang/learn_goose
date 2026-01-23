"""
Server Routes Package

Route modules for the goose-server:
- agent: Agent lifecycle management
- session: Session management
- recipe: Recipe management
- config: Configuration management
- status: Health checks and status
"""

from .router import ServerRouter, create_server_router
from . import agent, session, recipe, config, status
from .agent import router as agent_router
from .session import router as session_router
from .recipe import router as recipe_router
from .config import router as config_router
from .status import router as status_router

__all__ = [
    "ServerRouter",
    "create_server_router",
    "agent",
    "session",
    "recipe",
    "config",
    "status",
    "agent_router",
    "session_router",
    "recipe_router",
    "config_router",
    "status_router",
]
