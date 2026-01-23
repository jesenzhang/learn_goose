"""
Server Routes - Status

API endpoints for server status and health checks:
- Health check
- Server info
- Version info

Reference: goose-rs/crates/goose-server/src/routes/status.rs
"""

from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

from .router import ServerRouter

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str


class VersionInfo(BaseModel):
    """Version information"""
    version: str
    name: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint
    
    Returns the server status and current timestamp.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/ready")
async def readiness_check() -> Dict[str, str]:
    """
    Readiness check endpoint
    
    Returns 200 when the server is ready to accept requests.
    """
    return {"status": "ready"}


@router.get("/version", response_model=VersionInfo)
async def get_version() -> VersionInfo:
    """
    Get server version information
    """
    return VersionInfo(
        version="0.1.0",
        name="goose-system",
    )


@router.get("/")
async def root() -> Dict[str, str]:
    """
    Root endpoint
    
    Returns basic server information.
    """
    return {
        "name": "goose-system",
        "version": "1.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


def routes() -> ServerRouter:
    """Create router with all status routes"""
    return ServerRouter(router)
