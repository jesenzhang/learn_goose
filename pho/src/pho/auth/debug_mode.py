"""
Debug mode authentication - Skip auth for testing.
"""

from typing import Optional

from .protocol import UserInfo, AuthMode


class DebugAuth:
    """
    Debug mode authentication provider.

    Skips actual authentication and returns a debug user.
    Useful for local testing and development.
    """

    mode = AuthMode.LOCAL
    enabled = True

    def __init__(self):
        """Initialize debug auth with default debug user."""
        self._user_id = "debug_user"
        self._user_info = UserInfo(
            user_id=self._user_id,
            username="debug_user",
            email=None,
            role="admin",
            is_active=True,
        )

    async def initialize(self) -> bool:
        """Initialize debug auth (always succeeds)."""
        return True

    async def health_check(self) -> bool:
        """Health check (always returns True)."""
        return True

    async def validate_token(self, token: str) -> Optional[UserInfo]:
        """
        Validate token (debug mode accepts any token).

        Args:
            token: The token to validate (ignored in debug mode)

        Returns:
            Debug user info
        """
        return self._user_info

    async def authenticate_user(
        self,
        username: str,
        password: str
    ) -> Optional[UserInfo]:
        """
        Authenticate user (debug mode accepts any credentials).

        Args:
            username: Username (ignored)
            password: Password (ignored)

        Returns:
            Debug user info
        """
        return self._user_info

    async def get_user(self, user_id: str) -> Optional[UserInfo]:
        """
        Get user by ID (debug mode always returns debug user).

        Args:
            user_id: User ID to look up

        Returns:
            Debug user info
        """
        return self._user_info

    async def create_token(self, user_id: str) -> str:
        """
        Create token (debug mode returns a fixed token).

        Args:
            user_id: User ID

        Returns:
            Fixed debug token
        """
        return "debug_token_fixed"

    async def revoke_token(self, token: str) -> bool:
        """
        Revoke token (debug mode is no-op).

        Args:
            token: Token to revoke

        Returns:
            True (no-op in debug mode)
        """
        return True

    async def list_users(self, limit: int = 100) -> list:
        """
        List users (debug mode returns debug user).

        Args:
            limit: Maximum number of users to return

        Returns:
            List containing debug user
        """
        return [self._user_info]

    @property
    def user_id(self) -> str:
        """Get debug user ID."""
        return self._user_id

    @property
    def user_info(self) -> UserInfo:
        """Get debug user info."""
        return self._user_info
