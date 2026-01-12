"""
用户认证和授权服务

提供用户认证、令牌管理和权限检查功能
"""

import logging
import uuid
from typing import Optional, Dict

from .models import User, UserRole
from .repository import UserRepository, SessionCollaboratorRepository
from .schemas import AuthUser, Permission

logger = logging.getLogger("pho.auth.services")


class AuthenticationService:
    """
    认证服务

    提供用户认证和令牌管理功能
    """

    def __init__(self, user_repository: Optional[UserRepository] = None):
        self.user_repository = user_repository or UserRepository()
        # 简化实现：内存存储令牌
        # 生产环境应该使用 Redis 或数据库
        self._tokens: Dict[str, str] = {}  # token -> user_id
        self._user_tokens: Dict[str, str] = {}  # user_id -> token

    async def authenticate_by_credentials(
        self,
        username: str,
        password: str
    ) -> Optional[AuthUser]:
        """
        通过凭据认证用户

        Args:
            username: 用户名
            password: 密码

        Returns:
            认证成功的用户对象，失败返回 None
        """
        user = await self.user_repository.get_user_by_username(username)
        if not user or not user.is_active:
            return None

        # 验证密码
        if not await self.user_repository.verify_password(user.id, password):
            return None

        return AuthUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active
        )

    async def authenticate_by_token(self, token: str) -> Optional[AuthUser]:
        """
        通过令牌认证用户

        Args:
            token: 认证令牌

        Returns:
            认证成功的用户对象，失败返回 None
        """
        user_id = self._tokens.get(token)
        if not user_id:
            return None

        user = await self.user_repository.get_user_by_id(user_id)
        if user and user.is_active:
            return AuthUser(
                id=user.id,
                username=user.username,
                email=user.email,
                display_name=user.display_name,
                role=user.role,
                is_active=user.is_active
            )
        return None

    async def create_token(self, user_id: str) -> str:
        """
        为用户创建认证令牌

        Args:
            user_id: 用户 ID

        Returns:
            认证令牌
        """
        # 简化实现：生成随机令牌
        # 生产环境应该使用 JWT
        token = uuid.uuid4().hex + uuid.uuid4().hex

        # 使该用户的旧令牌失效
        old_token = self._user_tokens.get(user_id)
        if old_token:
            del self._tokens[old_token]

        self._tokens[token] = user_id
        self._user_tokens[user_id] = token

        logger.debug(f"Created token for user {user_id}")
        return token

    async def revoke_token(self, token: str) -> bool:
        """
        撤销认证令牌

        Args:
            token: 要撤销的令牌

        Returns:
            是否成功撤销
        """
        user_id = self._tokens.pop(token, None)
        if user_id:
            self._user_tokens.pop(user_id, None)
            logger.debug(f"Revoked token for user {user_id}")
            return True
        return False

    async def verify_token(self, token: str) -> bool:
        """
        验证令牌是否有效

        Args:
            token: 要验证的令牌

        Returns:
            令牌是否有效
        """
        return token in self._tokens


class AuthorizationService:
    """
    授权服务

    提供权限检查功能
    """

    def __init__(
        self,
        user_repository: Optional[UserRepository] = None,
        collaborator_repository: Optional[SessionCollaboratorRepository] = None
    ):
        self.user_repository = user_repository or UserRepository()
        self.collaborator_repository = (
            collaborator_repository or SessionCollaboratorRepository()
        )

    async def check_permission(
        self,
        user_id: str,
        required_permission: Permission,
        resource_id: Optional[str] = None
    ) -> bool:
        """
        检查用户是否有指定权限

        Args:
            user_id: 用户 ID
            required_permission: 需要的权限
            resource_id: 资源 ID（可选，用于资源级权限检查）

        Returns:
            是否有权限
        """
        user = await self.user_repository.get_user_by_id(user_id)
        if not user or not user.is_active:
            return False

        auth_user = AuthUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active
        )

        return auth_user.has_permission(required_permission)

    async def check_session_access(
        self,
        user_id: str,
        session_id: str,
        session_repository
    ) -> bool:
        """
        检查用户是否可访问会话

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            session_repository: 会话仓储

        Returns:
            是否可访问
        """
        # 检查用户是否是会话所有者或协作者
        return await session_repository.is_session_accessible(session_id, user_id)


# ================= 全局单例 =================

_global_user_repository: Optional[UserRepository] = None
_global_collaborator_repository: Optional[SessionCollaboratorRepository] = None
_global_auth_service: Optional[AuthenticationService] = None
_global_authz_service: Optional[AuthorizationService] = None


def get_user_repository() -> UserRepository:
    """获取全局用户仓储"""
    global _global_user_repository
    if _global_user_repository is None:
        _global_user_repository = UserRepository()
    return _global_user_repository


def get_collaborator_repository() -> SessionCollaboratorRepository:
    """获取全局协作者仓储"""
    global _global_collaborator_repository
    if _global_collaborator_repository is None:
        _global_collaborator_repository = SessionCollaboratorRepository()
    return _global_collaborator_repository


def get_auth_service() -> AuthenticationService:
    """获取全局认证服务"""
    global _global_auth_service
    if _global_auth_service is None:
        _global_auth_service = AuthenticationService(get_user_repository())
    return _global_auth_service


def get_authz_service() -> AuthorizationService:
    """获取全局授权服务"""
    global _global_authz_service
    if _global_authz_service is None:
        _global_authz_service = AuthorizationService(
            get_user_repository(),
            get_collaborator_repository()
        )
    return _global_authz_service
