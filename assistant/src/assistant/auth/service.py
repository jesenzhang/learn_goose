"""
用户认证和授权服务

提供用户认证、令牌管理和权限检查功能
"""

import logging
import time
import uuid
import hashlib
from typing import Optional, Dict, List

from .models import User, AuthUser, UserRole, CreateUserRequest, UpdateUserRequest, Permission
from ..db import get_db

logger = logging.getLogger(__name__)


class UserRepository:
    """
    用户仓储接口（基于 assistant 的数据库层）
    """

    async def create_user(self, request: CreateUserRequest) -> User:
        """创建新用户"""
        db = get_db()

        # 检查用户名是否已存在
        users = await db.list_all_users()
        for u in users:
            if u.get('user_id') == request.username or u.get('username') == request.username:
                raise ValueError(f"Username '{request.username}' already exists")

        # 生成密码哈希
        password_hash = None
        if request.password:
            password_hash = self._hash_password(request.password)

        now = time.time()
        user = User(
            id=request.username,  # 使用 username 作为 ID
            username=request.username,
            email=request.email,
            password_hash=password_hash,
            display_name=request.display_name or request.username,
            role=request.role,
            is_active=True,
            created_at=now,
            updated_at=now
        )

        # 保存到数据库（通过创建一个虚拟会话来存储用户信息）
        # 在 sessions 表中存储用户元数据
        user_data = {
            'user_id': user.username,
            'username': user.username,
            'email': user.email,
            'password_hash': password_hash,
            'display_name': user.display_name,
            'role': user.role.value,
            'is_active': user.is_active,
            'created_at': user.created_at,
            'updated_at': user.updated_at
        }

        # 使用特殊的 session_id 来存储用户数据
        await db.save_state_for_user(
            user.username,
            f"_user_{user.username}",
            {
                '_type': 'user',
                '_data': user_data
            }
        )

        logger.info(f"Created user: {user.username}")
        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据用户 ID 获取用户"""
        db = get_db()

        # 尝试从数据库加载用户数据
        state = await db.load_state_for_user(user_id, f"_user_{user_id}")
        if state and state.get('_type') == 'user':
            data = state.get('_data', {})
            return User(
                id=data.get('user_id', user_id),
                username=data.get('username', user_id),
                email=data.get('email'),
                password_hash=data.get('password_hash'),
                display_name=data.get('display_name'),
                role=UserRole(data.get('role', 'user')),
                is_active=data.get('is_active', True),
                created_at=data.get('created_at', 0),
                updated_at=data.get('updated_at', 0)
            )

        # 检查是否是默认用户（从会话列表中推断）
        sessions = await db.list_sessions_for_user(user_id, limit=1)
        if sessions:
            # 用户存在但没有正式注册，返回默认用户
            return User(
                id=user_id,
                username=user_id,
                email=None,
                password_hash=None,
                display_name=user_id,
                role=UserRole.USER,
                is_active=True,
                created_at=time.time(),
                updated_at=time.time()
            )

        return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return await self.get_user_by_id(username)

    async def list_users(self, limit: int = 100) -> List[User]:
        """列出所有用户"""
        db = get_db()
        users_data = await db.list_all_users()

        users = []
        for u in users_data[:limit]:
            user_id = u.get('user_id')
            if user_id and user_id != 'default':
                user = await self.get_user_by_id(user_id)
                if user:
                    users.append(user)

        return users

    async def update_user_role(
        self,
        user_id: str,
        new_role: UserRole
    ) -> Optional[User]:
        """更新用户角色"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        user.role = new_role
        user.updated_at = time.time()

        # 更新数据库
        db = get_db()
        await db.save_state_for_user(
            user_id,
            f"_user_{user_id}",
            {
                '_type': 'user',
                '_data': user.model_dump()
            }
        )

        logger.info(f"Updated user {user_id} role to {new_role}")
        return user

    async def deactivate_user(self, user_id: str) -> bool:
        """停用用户"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        user.is_active = False
        user.updated_at = time.time()

        # 更新数据库
        db = get_db()
        await db.save_state_for_user(
            user_id,
            f"_user_{user_id}",
            {
                '_type': 'user',
                '_data': user.model_dump()
            }
        )

        logger.info(f"Deactivated user {user_id}")
        return True

    async def verify_password(self, user_id: str, password: str) -> bool:
        """验证用户密码"""
        user = await self.get_user_by_id(user_id)
        if not user or not user.password_hash:
            return False

        return user.password_hash == self._hash_password(password)

    async def change_password(self, user_id: str, new_password: str) -> bool:
        """修改用户密码"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        user.password_hash = self._hash_password(new_password)
        user.updated_at = time.time()

        # 更新数据库
        db = get_db()
        await db.save_state_for_user(
            user_id,
            f"_user_{user_id}",
            {
                '_type': 'user',
                '_data': user.model_dump()
            }
        )

        logger.info(f"Changed password for user {user_id}")
        return True

    def _hash_password(self, password: str) -> str:
        """
        密码哈希（简化实现）

        生产环境应该使用 bcrypt 或 argon2
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def to_auth_user(self, user: User) -> AuthUser:
        """将 User 转换为 AuthUser（不包含敏感信息）"""
        return AuthUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active
        )


class AuthenticationService:
    """
    认证服务

    提供用户认证和令牌管理功能
    """

    def __init__(self):
        self.user_repository = UserRepository()
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

        return self.user_repository.to_auth_user(user)

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
            return self.user_repository.to_auth_user(user)
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

    def __init__(self):
        self.user_repository = UserRepository()

    async def check_permission(
        self,
        user_id: str,
        required_permission: Permission
    ) -> bool:
        """
        检查用户是否有指定权限

        Args:
            user_id: 用户 ID
            required_permission: 需要的权限

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

        role_permissions = {
            UserRole.GUEST: [Permission.READ],
            UserRole.USER: [Permission.READ, Permission.WRITE],
            UserRole.ADMIN: [Permission.READ, Permission.WRITE, Permission.ADMIN],
        }

        user_permissions = role_permissions.get(user.role, [])
        return required_permission in user_permissions


# ================= 全局单例 =================

_global_auth_service: Optional[AuthenticationService] = None
_global_authz_service: Optional[AuthorizationService] = None


def get_auth_service() -> AuthenticationService:
    """获取全局认证服务"""
    global _global_auth_service
    if _global_auth_service is None:
        _global_auth_service = AuthenticationService()
    return _global_auth_service


def get_authz_service() -> AuthorizationService:
    """获取全局授权服务"""
    global _global_authz_service
    if _global_authz_service is None:
        _global_authz_service = AuthorizationService()
    return _global_authz_service
