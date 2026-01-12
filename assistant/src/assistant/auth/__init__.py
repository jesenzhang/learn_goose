"""
认证和授权模块

提供用户认证、角色管理和权限检查功能
"""

from .models import (
    UserRole,
    User,
    AuthUser,
    CreateUserRequest,
    UpdateUserRequest,
    Permission,
)
from .service import (
    UserRepository,
    AuthenticationService,
    AuthorizationService,
    get_auth_service,
    get_authz_service,
)

__all__ = [
    # 枚举
    "UserRole",
    "Permission",

    # 用户模型
    "User",
    "AuthUser",

    # 请求模型
    "CreateUserRequest",
    "UpdateUserRequest",

    # 服务
    "UserRepository",
    "AuthenticationService",
    "AuthorizationService",

    # 全局函数
    "get_auth_service",
    "get_authz_service",
]
