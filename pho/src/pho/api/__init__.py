"""
Pho API - Unified FastAPI application for multi-style agent framework.

This package provides RESTful and streaming endpoints for:
- Agent execution (all 5 styles)
- Workflow management
- Session management
"""

from pho.api.app import create_app, app, run_server
from pho.api.agent_routes import create_agent_router
from pho.api.workflow_routes import create_workflow_router

__all__ = [
    "create_app",
    "app",
    "run_server",
    "create_agent_router",
    "create_workflow_router",
]
