"""
认证和授权模块

提供用户认证、角色管理和权限检查功能

模块结构：
- models.py: 数据模型（User, SessionCollaborator 等）
- schemas.py: API Schema 和 DTO（CreateUserRequest, UpdateUserRequest, AuthUser 等）
- repository.py: 数据仓储（UserRepository, SessionCollaboratorRepository）
- services.py: 业务服务（AuthenticationService, AuthorizationService）
"""

from .models import (
    UserRole,
    CollaboratorRole,
    User,
    SessionCollaborator,
)

from .schemas import (
    Permission,
    AuthUser,
    CreateUserRequest,
    UpdateUserRequest,
    to_auth_user,
)

from .repository import (
    UserRepository,
    SessionCollaboratorRepository,
)

from .services import (
    AuthenticationService,
    AuthorizationService,
    get_user_repository,
    get_collaborator_repository,
    get_auth_service,
    get_authz_service,
)

__all__ = [
    # 枚举
    "UserRole",
    "CollaboratorRole",
    "Permission",

    # 数据模型
    "User",
    "SessionCollaborator",

    # API Schema
    "AuthUser",
    "CreateUserRequest",
    "UpdateUserRequest",
    "to_auth_user",

    # 仓储
    "UserRepository",
    "SessionCollaboratorRepository",

    # 服务
    "AuthenticationService",
    "AuthorizationService",

    # 全局函数
    "get_user_repository",
    "get_collaborator_repository",
    "get_auth_service",
    "get_authz_service",
]
