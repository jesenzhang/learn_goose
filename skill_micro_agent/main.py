"""
Skill MicroAgent - Main Application Entry Point

This is the main entry point for the refactored agent system.
It initializes the FastAPI application with proper lifecycle management.

Configuration:
    Loads from agent_config.yaml in the current directory
    Can be overridden with environment variables

Usage:
    python -m skill_micro_agent.main
    or
    uvicorn skill_micro_agent.main:app --host 0.0.0.0 --port 8300
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('skill_micro_agent.log', encoding='utf-8')
    ],
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

# Global agent instance
agent = None


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    from skill_micro_agent.config.loader import ConfigLoader
    from skill_micro_agent.db import get_db
    from skill_micro_agent.core.agent import MicroAgent
    from skill_micro_agent.api.routes import create_router, set_agent
    from ai_services import OpenAI_Service
    from skill_micro_agent.skills.loader import SkillLoader
    from skill_micro_agent.providers import ProviderFactory

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan manager."""
        global agent

        # Startup
        logger.info("Starting Skill MicroAgent...")
        try:
            # Initialize configuration
            config_path = os.getenv('AGENT_CONFIG', 'agent_config.yaml')
            config = ConfigLoader(config_path)

            # Initialize database
            db = get_db()
            logger.info("Database initialized")


            # Initialize agent
            agent = MicroAgent(
                config_path=config_path
            )
            set_agent(agent)
            logger.info("Agent initialized successfully")

            yield

        except Exception as e:
            logger.error(f"Failed to initialize application: {e}", exc_info=e)
            raise

        # Shutdown
        logger.info("Shutting down Skill MicroAgent...")
        if agent:
            try:
                agent.shutdown()
            except Exception as e:
                logger.error(f"Error during agent shutdown: {e}", exc_info=e)
        logger.info("Shutdown complete")

    # Create FastAPI app
    app = FastAPI(
        title="Skill MicroAgent",
        description="Event-driven LLM agent with tool execution",
        version="2.0.0",
        lifespan=lifespan
    )

    # Include routes
    router = create_router()
    app.include_router(router)

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "Skill MicroAgent",
            "version": "2.0.0",
            "status": "running",
            "endpoints": {
                "health": "GET /health",
                "chat": "POST /chat/{session_id}",
                "sessions": "GET /sessions",
                "state": "GET /agent/{session_id}/state",
                "approval": "POST /agent/{session_id}/approval"
            }
        }

    return app


# Create app instance
app = create_app()


def main():
    """
    Run the application directly.

    Configuration can be overridden via environment variables:
        - AGENT_PORT: Port to listen on (default: 8300)
        - AGENT_HOST: Host to bind to (default: 0.0.0.0)
        - AGENT_CONFIG: Path to config file (default: agent_config.yaml)
    """
    port = int(os.getenv('AGENT_PORT', 8300))
    host = os.getenv('AGENT_HOST', '0.0.0.0')

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(
        "skill_micro_agent.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
