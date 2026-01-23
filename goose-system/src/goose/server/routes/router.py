"""
Server Router Helper

Custom router class that extends FastAPI's APIRouter for consistency.
"""

from fastapi import APIRouter
from typing import Callable


class ServerRouter:
    """
    Server-specific router wrapper
    
    Provides consistent API router interface.
    """
    
    def __init__(self, router: APIRouter = None):
        self._router = router or APIRouter()
    
    def include_router(self, router: "ServerRouter", prefix: str = "", tags: list = None) -> None:
        """Include another router"""
        self._router.include_router(
            router._router,
            prefix=prefix,
            tags=tags,
        )
    
    def get_router(self) -> APIRouter:
        """Get the underlying FastAPI router"""
        return self._router


def create_server_router() -> ServerRouter:
    """Create a new server router"""
    return ServerRouter()
