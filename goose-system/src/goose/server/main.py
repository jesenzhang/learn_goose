"""
Goose Server Main Module

FastAPI-based HTTP server for goose-agent.

Features:
- REST API for agent management
- Session management endpoints
- Recipe loading and execution
- Configuration management
- API Key & Bearer Token authentication
- OpenAPI documentation

Usage:
    # X-Secret-Key authentication
    python -m goose.server.main --host 127.0.0.1 --port 8080 --secret-key your-secret-key
    
    # Bearer token authentication
    python -m goose.server.main --host 0.0.0.0 --port 8080 --token your-bearer-token
    
    # Both authentication methods
    python -m goose.server.main --secret-key key123 --token token456

Reference: goose-rs/crates/goose-server/src/main.rs
"""

import argparse
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger("goose.server")

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("FastAPI not available. Server functionality will be limited.")

try:
    from .auth import AuthMiddleware, APIKeyManager
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    AuthMiddleware = None
    APIKeyManager = None


@asynccontextmanager
async def lifespan(app: "FastAPI"):
    """Application lifespan manager"""
    logger.info("Starting goose-server...")
    yield
    logger.info("Shutting down goose-server...")


class AuthMiddlewareImpl(BaseHTTPMiddleware):
    """
    Authentication middleware implementation
    
    Supports two authentication methods:
    1. X-Secret-Key: <value>
    2. Authorization: Bearer <token>
    """
    
    EXCLUDED_PATHS = frozenset([
        "/health",
        "/ready",
        "/version",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
    ])
    
    def __init__(
        self,
        app,
        secret_key: str = "",
        token: str = "",
        auth_mode: str = "any",
    ):
        super().__init__(app)
        self.secret_key = secret_key
        self.token = token
        self.auth_mode = auth_mode
    
    def is_excluded_path(self, path: str) -> bool:
        if path.startswith("/mcp-ui-proxy"):
            return True
        if path.startswith("/mcp-app-proxy"):
            return True
        return path in self.EXCLUDED_PATHS
    
    def validate_secret_key(self, key: str) -> bool:
        return key == self.secret_key
    
    def validate_bearer_token(self, auth_header: str) -> bool:
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return token == self.token
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        
        if self.is_excluded_path(path):
            return await call_next(request)
        
        if not self.secret_key and not self.token:
            return await call_next(request)
        
        secret_key = request.headers.get("X-Secret-Key")
        auth_header = request.headers.get("Authorization")
        
        has_secret = secret_key and secret_key != ""
        has_bearer = auth_header and auth_header.startswith("Bearer ")
        
        if not has_secret and not has_bearer:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Missing authentication. "
                             "Provide X-Secret-Key header or Authorization: Bearer <token>"
                },
            )
        
        if self.auth_mode == "secret_key":
            if not has_secret or not self.validate_secret_key(secret_key):
                return JSONResponse(status_code=401, content={"detail": "Invalid X-Secret-Key"})
            return await call_next(request)
        
        if self.auth_mode == "bearer":
            if not has_bearer or not self.validate_bearer_token(auth_header):
                return JSONResponse(status_code=401, content={"detail": "Invalid Bearer token"})
            return await call_next(request)
        
        if self.auth_mode == "any":
            if has_secret and self.validate_secret_key(secret_key):
                return await call_next(request)
            if has_bearer and self.validate_bearer_token(auth_header):
                return await call_next(request)
            return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})
        
        return await call_next(request)


def create_app(
    title: str = "Goose System API",
    secret_key: str = "",
    token: str = "",
    auth_mode: str = "any",
) -> Optional["FastAPI"]:
    """
    Create and configure the FastAPI application
    
    Args:
        title: API title for OpenAPI docs
        secret_key: API secret key for X-Secret-Key header (optional)
        token: Bearer token for Authorization header (optional)
        auth_mode: Authentication mode
            - "any": Accept either X-Secret-Key or Bearer token
            - "secret_key": Require X-Secret-Key header only
            - "bearer": Require Authorization: Bearer only
        
    Returns:
        Configured FastAPI application or None if FastAPI not available
    """
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI is required. Install: pip install fastapi uvicorn")
        return None
    
    auth_enabled = secret_key or token
    auth_desc = ""
    if secret_key and token:
        auth_desc = "**Authentication**: X-Secret-Key header OR Authorization: Bearer token"
    elif secret_key:
        auth_desc = "**Authentication**: X-Secret-Key header required"
    elif token:
        auth_desc = "**Authentication**: Authorization: Bearer <token> required"
    
    app = FastAPI(
        title=title,
        description=f"Goose System API - Agent management and configuration\n\n"
                   f"{auth_desc}\n\n"
                   f"**Excluded paths**: /health, /ready, /version, /docs",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    if auth_enabled:
        app.add_middleware(
            AuthMiddlewareImpl,
            secret_key=secret_key,
            token=token,
            auth_mode=auth_mode,
        )
        
        if secret_key and token:
            logger.info("Authentication enabled: X-Secret-Key OR Bearer token")
        elif secret_key:
            logger.info("Authentication enabled: X-Secret-Key only")
        else:
            logger.info("Authentication enabled: Bearer token only")
    else:
        logger.warning("Authentication disabled - no credentials provided")
    
    try:
        from .routes import status, agent, session, recipe, config
        
        app.include_router(status.router, tags=["Status"])
        app.include_router(agent.router, prefix="/api/v1", tags=["Agent"])
        app.include_router(session.router, prefix="/api/v1", tags=["Session"])
        app.include_router(recipe.router, prefix="/api/v1", tags=["Recipe"])
        app.include_router(config.router, prefix="/api/v1", tags=["Config"])
        
        logger.info("Routes registered successfully")
        
    except Exception as e:
        logger.error(f"Failed to register routes: {e}")
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    
    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
    reload: bool = False,
    secret_key: str = "",
    token: str = "",
    auth_mode: str = "any",
) -> None:
    """
    Run the HTTP server
    
    Args:
        host: Server host address
        port: Server port
        debug: Enable debug mode
        reload: Enable auto-reload (development only)
        secret_key: API secret key for X-Secret-Key
        token: Bearer token for Authorization
        auth_mode: "any", "secret_key", or "bearer"
    """
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI is required to run the server")
        return
    
    import uvicorn
    
    app = create_app(
        secret_key=secret_key,
        token=token,
        auth_mode=auth_mode,
    )
    
    if app is None:
        logger.error("Failed to create FastAPI application")
        return
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="debug" if debug else "info",
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Goose System API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--secret-key",
        type=str,
        default="",
        help="API secret key for X-Secret-Key header",
    )
    auth_group.add_argument(
        "--token",
        type=str,
        default="",
        help="Bearer token for Authorization header",
    )
    auth_group.add_argument(
        "--auth-mode",
        type=str,
        default="any",
        choices=["any", "secret_key", "bearer"],
        help="Authentication mode (default: any)",
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level",
    )
    
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a new API key and exit",
    )
    
    parser.add_argument(
        "--generate-token",
        action="store_true",
        help="Generate a new Bearer token and exit",
    )
    
    args = parser.parse_args()
    
    if args.generate_key:
        if APIKeyManager:
            key = APIKeyManager.generate_key()
            print(f"Generated API key: {key}")
            print("\nUse with: python -m goose.server.main --secret-key {key}")
        else:
            print("APIKeyManager not available")
        return
    
    if args.generate_token:
        if APIKeyManager:
            token = APIKeyManager.generate_token()
            print(f"Generated Bearer token: {token}")
            print("\nUse with: python -m goose.server.main --token {token}")
        else:
            print("APIKeyManager not available")
        return
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger.info(f"Starting goose-server on {args.host}:{args.port}")
    
    if args.secret_key or args.token:
        logger.info(f"Authentication mode: {args.auth_mode}")
        if args.secret_key:
            logger.info(f"  - X-Secret-Key: {'*' * len(args.secret_key)}")
        if args.token:
            logger.info(f"  - Bearer token: {'*' * len(args.token)}")
    else:
        logger.warning("Authentication: DISABLED")
    
    run_server(
        host=args.host,
        port=args.port,
        debug=args.debug,
        reload=args.reload,
        secret_key=args.secret_key,
        token=args.token,
        auth_mode=args.auth_mode,
    )


if __name__ == "__main__":
    main()
