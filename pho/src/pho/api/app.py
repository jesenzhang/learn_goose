"""
Pho FastAPI Application - Main application factory.

This module provides the main FastAPI application with:
- Multi-style agent execution endpoints
- Workflow management endpoints
- CORS middleware
- Global error handling
- Lifecycle management
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from pho.api.agent_routes import create_agent_router
from pho.api.workflow_routes import create_workflow_router
from pho.api.component_routes import router as component_router

logger = logging.getLogger(__name__)


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("🌱 Pho API starting up...")
    logger.info("   - Agent routes initialized")
    logger.info("   - Workflow routes initialized")
    logger.info("   - Component routes initialized")
    logger.info("   - In-memory storage active")

    yield

    # Shutdown
    logger.info("🛑 Pho API shutting down...")


# ============================================================================
# Application Factory
# ============================================================================

def create_app(
    title: str = "Pho API",
    version: str = "0.1.0",
    description: Optional[str] = None,
    cors_origins: Optional[list] = None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        title: API title
        version: API version
        description: API description
        cors_origins: List of allowed CORS origins

    Returns:
        Configured FastAPI application
    """
    if description is None:
        description = """
        Pho - Unified AI Agent Framework

        Multi-style agent system supporting:
        - **BaseAgent**: Simple LLM + tools
        - **StreamingAgent**: Event-driven streaming (Goose-rs style)
        - **ReactAgent**: Thought → Action → Observation loop (Claude Code style)
        - **ThreePhaseAgent**: Intent → LLM → Tools (Skill Micro Agent style)
        - **WorkflowAgent**: DAG workflow orchestration (Goose-py style)

        Features:
        - RESTful API for agent execution
        - Server-Sent Events (SSE) for streaming
        - Workflow management and execution
        - Session management
        - Multi-provider LLM support
        """

    if cors_origins is None:
        cors_origins = ["*"]  # Allow all origins in development

    # Create app
    app = FastAPI(
        title=title,
        version=version,
        description=description,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ========================================================================
    # Middleware
    # ========================================================================

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ========================================================================
    # Global Exception Handler
    # ========================================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle uncaught exceptions."""
        logger.error(f"Unhandled exception: {exc}", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "Internal Server Error",
                "detail": str(exc),
            },
        )

    # ========================================================================
    # Root Endpoints
    # ========================================================================

    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Pho API",
            "version": version,
            "description": "Unified AI Agent Framework",
            "docs": "/docs",
            "health": "/health",
            "agent_health": "/api/v1/agent/health",
            "workflow_health": "/api/v1/workflows/health",
        }

    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "service": "pho-api",
            "version": version,
        }

    # ========================================================================
    # Router Registration
    # ========================================================================

    # Agent routes
    agent_router = create_agent_router()
    app.include_router(agent_router)

    # Workflow routes
    workflow_router = create_workflow_router()
    app.include_router(workflow_router)

    # Component routes
    app.include_router(component_router)

    logger.info("✅ FastAPI application created")

    return app


# ============================================================================
# Default Application Instance
# ============================================================================

# Create default app for direct import
app = create_app()


# ============================================================================
# Entry Point
# ============================================================================

def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    log_level: str = "info",
):
    """
    Run the API server.

    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload
        log_level: Logging level
    """
    import uvicorn

    uvicorn.run(
        "pho.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    # Run server when executed directly
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    run_server(reload=True)
