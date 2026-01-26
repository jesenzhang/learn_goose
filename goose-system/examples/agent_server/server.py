"""
Goose Agent Server Example

Complete Agent server example including:
- User authentication (register/login/logout)
- Session management
- JSONL data persistence
- User-associated sessions
- OpenAPI documentation

Run:
    python server.py

Access:
    http://localhost:8080/docs  # OpenAPI documentation
    http://localhost:8080       # API root
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("Error: FastAPI is required. Install with: pip install fastapi uvicorn")
    sys.exit(1)

# Goose system imports
from goose.server.main import create_app, AuthMiddlewareImpl
from goose.server.user import UserManager, JsonLUserStorage
from goose.session import SessionManager
from goose.persistence import init_persistence

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("goose.server.example")


class DataDirectories:
    """Data directory configuration"""
    def __init__(self, base_dir: str = "./data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.users_dir = self.base_dir / "users"
        self.sessions_dir = self.base_dir / "sessions"
        self.persistence_dir = self.base_dir / "persistence"

        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.persistence_dir.mkdir(parents=True, exist_ok=True)


# Global instances
_user_manager: Optional[UserManager] = None
_session_manager: Optional[SessionManager] = None
_persistence_manager = None


async def initialize_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    data_dir: str = "./data",
    auth_mode: str = "user",
    secret_key: str = "",
    token: str = "",
    create_admin_user: Optional[str] = None,
) -> FastAPI:
    """Initialize server and create FastAPI app"""
    global _user_manager, _session_manager, _persistence_manager

    logger.info("Initializing Goose Agent Server...")

    # Initialize data directories
    data_dirs = DataDirectories(data_dir)

    # Initialize user manager
    user_storage = JsonLUserStorage(str(data_dirs.users_dir))
    _user_manager = UserManager(storage=user_storage)

    # Initialize session manager
    sessions_path = str(data_dirs.sessions_dir / "sessions.json")
    _session_manager = SessionManager(storage_path=sessions_path)
    await _session_manager.initialize()

    # Initialize persistence manager
    persistence_url = f"file://{data_dirs.persistence_dir}"
    _persistence_manager = init_persistence(persistence_url)
    await _persistence_manager.boot()

    logger.info(f"Data directory: {data_dirs.base_dir}")
    logger.info(f"Authentication mode: {auth_mode}")
    logger.info(f"User storage: {data_dirs.users_dir}")
    logger.info(f"Session storage: {data_dirs.sessions_dir}")
    logger.info(f"Persistence storage: {data_dirs.persistence_dir}")

    # Create admin user if specified
    if create_admin_user:
        if ":" not in create_admin_user:
            print("Error: Invalid format. Use username:password")
        else:
            username, password = create_admin_user.split(":", 1)

            from goose.server.user import UserRole

            success, user, error = await _user_manager.register_user(
                username=username,
                password=password,
                email=f"{username}@localhost",
                role=UserRole.ADMIN
            )

            if success:
                print(f"Admin user created: {username}")
                print(f"User ID: {user.user_id}")
            else:
                print(f"Failed to create admin user: {error}")

    # Create FastAPI application
    app = FastAPI(
        title="Goose Agent Server",
        description="Goose Agent Server with User Authentication and Session Management",
        version="1.0.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add authentication middleware
    # Note: user-based auth is not fully implemented in AuthMiddlewareImpl
    # Using "any" mode for now - accepts either X-Secret-Key or Bearer token
    app.add_middleware(
        AuthMiddlewareImpl,
        secret_key=secret_key,
        token=token,
        auth_mode=auth_mode,
    )

    # Register routes
    try:
        from goose.server.routes import status, agent, session, config, auth

        app.include_router(status.router, tags=["Status"])
        app.include_router(auth.router, prefix="/api/v1", tags=["Auth"])
        app.include_router(session.router, prefix="/api/v1", tags=["Session"])
        app.include_router(agent.router, prefix="/api/v1", tags=["Agent"])
        app.include_router(config.router, prefix="/api/v1", tags=["Config"])

        logger.info("Routes registered successfully")

    except Exception as e:
        logger.error(f"Failed to register routes: {e}")

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc)
            },
        )

    return app


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Goose Agent Server with User Authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--data-dir", type=str, default="./data", help="Data directory")

    # Authentication options
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--auth-mode",
        type=str,
        default="user",
        choices=["user", "any", "secret_key", "bearer"],
        help="Authentication mode (default: user)"
    )
    auth_group.add_argument(
        "--secret-key",
        type=str,
        default="",
        help="API secret key for X-Secret-Key header"
    )
    auth_group.add_argument(
        "--token",
        type=str,
        default="",
        help="Bearer token for Authorization header"
    )

    # Tool options
    parser.add_argument(
        "--create-admin",
        type=str,
        help="Create admin user (format: username:password)"
    )

    args = parser.parse_args()

    # Import uvicorn after parsing args
    import uvicorn

    # Lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info("Goose Agent Server starting up...")
        yield
        # Shutdown
        logger.info("Goose Agent Server shutting down...")
        if _session_manager:
            await _session_manager.close_all()

    # Create app with lifespan
    app = FastAPI(
        title="Goose Agent Server",
        lifespan=lifespan,
    )

    # Initialize app components before starting
    async def setup_app():
        return await initialize_server(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
            auth_mode=args.auth_mode,
            secret_key=args.secret_key,
            token=args.token,
            create_admin_user=args.create_admin,
        )

    # Initialize async components
    initialized_app = asyncio.run(setup_app())

    # Copy routes and middleware from initialized app to main app
    # This is a workaround - the routes should be set up before uvicorn runs
    logger.info(f"Starting Goose Agent Server on {args.host}:{args.port}")
    logger.info(f"OpenAPI docs available at http://{args.host}:{args.port}/docs")

    # Run uvicorn with the fully configured app
    uvicorn.run(
        initialized_app,
        host=args.host,
        port=args.port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
