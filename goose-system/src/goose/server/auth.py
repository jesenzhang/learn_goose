"""
Server Authentication Module

API Key based authentication:
- X-Secret-Key header validation
- Authorization: Bearer token validation
- Secret key configuration
- Secure route protection

Reference: goose-rs/crates/goose-server/src/auth.rs
"""

import logging
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("goose.server.auth")


class AuthMiddleware:
    """
    Authentication middleware for API key validation
    
    Supports two authentication methods:
    1. X-Secret-Key header (custom, simple)
    2. Authorization: Bearer <token> (standard OAuth2 style)
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
        secret_key: str = "",
        token: str = "",
        auth_mode: str = "any",
    ):
        """
        Initialize auth middleware
        
        Args:
            secret_key: API secret key for X-Secret-Key header validation
            token: Bearer token for Authorization header validation
            auth_mode: Authentication mode
                - "any": Accept either X-Secret-Key or Bearer token
                - "secret_key": Require X-Secret-Key header only
                - "bearer": Require Authorization: Bearer token only
        """
        self.secret_key = secret_key
        self.token = token
        self.auth_mode = auth_mode
    
    def is_excluded_path(self, path: str) -> bool:
        """Check if path is excluded from auth"""
        if path.startswith("/mcp-ui-proxy"):
            return True
        if path.startswith("/mcp-app-proxy"):
            return True
        return path in self.EXCLUDED_PATHS
    
    def validate_secret_key(self, secret_key: str) -> bool:
        """Validate X-Secret-Key header value"""
        return secret_key == self.secret_key
    
    def validate_bearer_token(self, auth_header: str) -> bool:
        """Validate Authorization: Bearer token"""
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]  # Remove "Bearer " prefix
        return token == self.token
    
    def get_credentials_from_request(self, request: Request) -> tuple:
        """
        Extract credentials from request
        
        Returns:
            (has_secret_key, secret_key, has_bearer, bearer_token)
        """
        secret_key = request.headers.get("X-Secret-Key")
        auth_header = request.headers.get("Authorization")
        
        has_secret_key = secret_key is not None and secret_key != ""
        has_bearer = auth_header is not None and auth_header.startswith("Bearer ")
        
        return (
            has_secret_key,
            secret_key if has_secret_key else "",
            has_bearer,
            auth_header[7:] if has_bearer else ""
        )
    
    async def validate_request(self, request: Request) -> str:
        """
        Validate request authentication
        
        Supports:
        - X-Secret-Key: <value>
        - Authorization: Bearer <token>
        
        Args:
            request: FastAPI request
            
        Returns:
            The validated credential type ("secret_key" or "bearer")
            
        Raises:
            HTTPException: If authentication fails
        """
        path = request.url.path
        
        if self.is_excluded_path(path):
            return "none"
        
        if not self.secret_key and not self.token:
            logger.warning(f"Authentication disabled, no credentials configured")
            return "none"
        
        has_secret_key, secret_key, has_bearer, bearer_token = self.get_credentials_from_request(request)
        
        # No credentials provided
        if not has_secret_key and not has_bearer:
            logger.warning(f"Missing credentials for {path}")
            raise HTTPException(
                status_code=status.HTTP_UNAUTHORIZED,
                detail="Missing authentication. Provide X-Secret-Key header or Authorization: Bearer <token>",
            )
        
        # Mode: secret_key only
        if self.auth_mode == "secret_key":
            if not has_secret_key:
                raise HTTPException(
                    status_code=status.HTTP_UNAUTHORIZED,
                    detail="X-Secret-Key header required",
                )
            if not self.validate_secret_key(secret_key):
                raise HTTPException(
                    status_code=status.HTTP_UNAUTHORIZED,
                    detail="Invalid X-Secret-Key",
                )
            return "secret_key"
        
        # Mode: bearer only
        if self.auth_mode == "bearer":
            if not has_bearer:
                raise HTTPException(
                    status_code=status.HTTP_UNAUTHORIZED,
                    detail="Authorization: Bearer <token> header required",
                )
            if not self.validate_bearer_token(f"Bearer {bearer_token}"):
                raise HTTPException(
                    status_code=status.HTTP_UNAUTHORIZED,
                    detail="Invalid Bearer token",
                )
            return "bearer"
        
        # Mode: any (default) - accept either
        if has_secret_key and self.validate_secret_key(secret_key):
            return "secret_key"
        
        if has_bearer and self.validate_bearer_token(f"Bearer {bearer_token}"):
            return "bearer"
        
        # Neither matched
        logger.warning(f"Invalid credentials for {path}")
        raise HTTPException(
            status_code=status.HTTP_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )


class APIKeyManager:
    """
    API Key and Token management
    """
    
    @staticmethod
    def generate_key(length: int = 32) -> str:
        """
        Generate a new API key (random string)
        
        Args:
            length: Key length in characters
            
        Returns:
            Generated API key
        """
        import secrets
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_token(length: int = 64) -> str:
        """
        Generate a new Bearer token (JWT-style random string)
        
        Args:
            length: Token length in characters
            
        Returns:
            Generated Bearer token
        """
        import secrets
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        return "".join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def validate_key_format(key: str) -> bool:
        """
        Validate API key format
        
        Args:
            key: API key to validate
            
        Returns:
            True if format is valid
        """
        if not key:
            return False
        if len(key) < 16:
            return False
        if not all(c.isalnum() or c in "-_" for c in key):
            return False
        return True
    
    @staticmethod
    def validate_token_format(token: str) -> bool:
        """
        Validate Bearer token format
        
        Args:
            token: Token to validate
            
        Returns:
            True if format is valid
        """
        if not token:
            return False
        if len(token) < 32:
            return False
        return True


def create_auth_dependency(
    secret_key: str = "",
    token: str = "",
    auth_mode: str = "any",
) -> Callable:
    """
    Create authentication dependency for FastAPI routes
    
    Args:
        secret_key: API secret key for X-Secret-Key validation
        token: Bearer token for Authorization validation
        auth_mode: "any", "secret_key", or "bearer"
        
    Returns:
        Dependency function that validates authentication
    """
    async def verify_credentials(request: Request) -> str:
        auth = AuthMiddleware(secret_key, token, auth_mode)
        return await auth.validate_request(request)
    
    return verify_credentials


def verify_api_key(
    secret_key: str = "",
    token: str = "",
    auth_mode: str = "any",
) -> Callable:
    """
    Create dependency that verifies credentials
    
    Args:
        secret_key: Expected API secret key
        token: Expected Bearer token
        auth_mode: Authentication mode
        
    Returns:
        FastAPI dependency returning credential type
    """
    async def dependency(request: Request) -> str:
        auth = AuthMiddleware(secret_key, token, auth_mode)
        return await auth.validate_request(request)
    
    return dependency


class TokenValidator:
    """
    JWT-style token validation utilities
    """
    
    @staticmethod
    def extract_bearer_token(auth_header: str) -> Optional[str]:
        """
        Extract token from Authorization header
        
        Args:
            auth_header: Authorization header value
            
        Returns:
            Token string or None if invalid format
        """
        if not auth_header:
            return None
        if not auth_header.startswith("Bearer "):
            return None
        return auth_header[7:]
    
    @staticmethod
    def create_auth_response(
        token: str,
        expires_in: int = 3600,
        token_type: str = "Bearer",
    ) -> dict:
        """
        Create standard OAuth2 token response
        
        Args:
            token: Access token
            expires_in: Expiration time in seconds
            token_type: Token type (Bearer)
            
        Returns:
            Token response dictionary
        """
        import time
        return {
            "access_token": token,
            "token_type": token_type,
            "expires_in": expires_in,
            "expires_at": int(time.time()) + expires_in,
        }


# Convenience function to get credentials from request
async def get_authenticated_credentials(request: Request) -> dict:
    """
    Get authenticated credentials from request
    
    Returns dict with:
    - credential_type: "secret_key" or "bearer"
    - credentials: The raw credentials provided
    
    Args:
        request: FastAPI request
        
    Returns:
        Credentials dictionary
    """
    auth = AuthMiddleware()
    has_secret_key, secret_key, has_bearer, bearer_token = auth.get_credentials_from_request(request)
    
    if has_secret_key:
        return {"type": "secret_key", "value": secret_key}
    if has_bearer:
        return {"type": "bearer", "value": bearer_token}
    
    return {"type": "none", "value": None}
