"""
Goose Server Module

FastAPI-based HTTP server for goose-agent, providing:
- REST API for agent management
- Session management endpoints
- Recipe loading and execution
- Configuration management
- OpenAPI documentation

Reference: goose-rs/crates/goose-server/src/
"""

from .main import create_app, run_server
from .state import AppState, create_app_state
from .routes import agent, session, recipe, config, status

__all__ = [
    "create_app",
    "run_server",
    "AppState",
    "create_app_state",
    "agent",
    "session",
    "recipe",
    "config",
    "status",
]
