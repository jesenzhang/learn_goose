"""
Authentication Module - 可插拔的用户认证系统

支持两种认证模式：
1. Local (本地模式): 使用 assistant 内置数据库和用户验证
2. External (外置模式): 通过 token 进行认证，用户管理在外部系统

设计原则：
- Protocol-based: 基于协议定义，确保接口一致性
- Pluggable: 支持运行时切换认证提供者
- Separation of concerns: 认证逻辑与业务逻辑分离
"""

from .protocol import (
    # Enums
    AuthMode,
    UserRole,
    # Data Classes
    UserInfo,
    AuthConfig,

    # Protocols
    AuthProvider,
    TokenAuth,
    UserAuth,
)

from .local_provider import LocalAuthProvider
from .external_provider import ExternalAuthProvider
from .registry import (
    AuthProviderRegistry,
    init_registry,
    get_registry,
    reset_registry,
)

__all__ = [
    # Enum
    "AuthMode",

    # Data Classes
    "UserInfo",
    "AuthConfig",

    # Protocols
    "AuthProvider",
    "TokenAuth",
    "UserAuth",

    # Implementations
    "LocalAuthProvider",
    "ExternalAuthProvider",

    # Registry
    "AuthProviderRegistry",
    "init_registry",
    "get_registry",
    "reset_registry",
]
