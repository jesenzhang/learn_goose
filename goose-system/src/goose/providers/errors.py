"""
Provider Errors

Error types for provider operations.
Reference: assistant providers errors implementation.
"""

from typing import Optional


class ProviderError(Exception):
    """Base provider error."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(ProviderError):
    """Authentication failed error."""
    pass


class RequestFailedError(ProviderError):
    """Request failed error (rate limit, timeout, connection)."""
    pass


class ContextLengthExceededError(ProviderError):
    """Context length exceeded error."""
    pass


class UsageError(ProviderError):
    """Usage-related error."""
    pass


class ExecutionError(ProviderError):
    """Execution error."""
    pass


class NotImplementedError(ProviderError):
    """Not implemented error."""
    pass
