"""
Authentication Protocol - 用户认证协议定义

定义所有认证提供者必须遵循的接口契约。

支持两种认证模式：
1. Local (本地模式): 使用 assistant 内置数据库和用户验证
2. External (外置模式): 通过 token 进行认证，用户管理在外部系统
"""

from typing import Protocol, Dict, Any, Optional, runtime_checkable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# ================= 数据模型 =================


class AuthMode(str, Enum):
    """认证模式"""
    LOCAL = "local"       # 本地模式：使用内置数据库
    EXTERNAL = "external"   # 外置模式：通过外部系统认证

class UserRole(str, Enum):
    """认证模式"""
    USER = "user"       # 本地模式：使用内置数据库
    ADMIN = "admin"   # 外置模式：通过外部系统认证
    GUEST = "guest"   # 外置模式：通过外部系统认证

@dataclass
class UserInfo:
    """
    用户信息数据类

    统一的用户信息格式，用于内部传递。
    """
    user_id: str           # 用户唯一标识
    username: str           # 用户名
    display_name: str        # 显示名称
    email: Optional[str]      # 邮箱（可选）
    permissions: Dict[str, bool]  # 权限信息
    created_at: datetime    # 创建时间
    last_active: datetime  # 最后活跃时间
    metadata: Dict[str, Any] = None  # 额外的元数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "permissions": self.permissions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "metadata": self.metadata or {}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserInfo":
        """从字典创建"""
        return cls(
            user_id=data.get("user_id", data.get("id", "")),
            username=data.get("username", ""),
            display_name=data.get("display_name", data.get("name", "")),
            email=data.get("email"),
            permissions=data.get("permissions", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else None,
            metadata=data.get("metadata")
        )


@dataclass
class AuthConfig:
    """
    认证配置

    定义认证系统的行为模式。
    """
    enabled: bool = True                      # 是否启用认证
    mode: AuthMode = AuthMode.LOCAL          # 认证模式：local 或 external
    external_auth_url: Optional[str] = None    # 外部认证服务 URL
    external_auth_api_key: Optional[str] = None  # 外部认证 API 密钥
    external_auth_timeout: int = 30            # 外部认证超时时间（秒）
    local_db_path: Optional[str] = None         # 本地数据库路径
    token_header_name: str = "Authorization"   # Token 请求头名称
    token_prefix: str = "Bearer"              # Token 前缀（如 Bearer）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "mode": self.mode.value,
            "external_auth_url": self.external_auth_url,
            "external_auth_api_key": self.external_auth_api_key,
            "external_auth_timeout": self.external_auth_timeout,
            "local_db_path": self.local_db_path,
            "token_header_name": self.token_header_name,
            "token_prefix": self.token_prefix,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthConfig":
        """从字典创建"""
        mode_str = data.get("mode", "local")
        try:
            mode = AuthMode(mode_str.lower())
        except ValueError:
            mode = AuthMode.LOCAL

        return cls(
            enabled=data.get("enabled", True),
            mode=mode,
            external_auth_url=data.get("external_auth_url"),
            external_auth_api_key=data.get("external_auth_api_key"),
            external_auth_timeout=data.get("external_auth_timeout", 30),
            local_db_path=data.get("local_db_path"),
            token_header_name=data.get("token_header_name", "Authorization"),
            token_prefix=data.get("token_prefix", "Bearer")
        )

@runtime_checkable
class AuthProvider(Protocol):
    """
    认证提供者协议

    所有认证提供者必须实现此接口。
    """

    async def initialize(self) -> bool:
        """
        初始化认证提供者

        Returns:
            是否初始化成功
        """
        ...

    async def close(self) -> None:
        """关闭认证提供者，释放资源"""
        ...

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康可用
        """
        ...


class TokenAuth(AuthProvider):
    """
    Token 认证协议 - 用于外置模式

    通过 token 验证用户身份，并获取用户信息。
    """

    async def validate_token(self, token: str) -> Optional[UserInfo]:
        """
        验证 token 并返回用户信息

        Args:
            token: 认证 token

        Returns:
            用户信息，如果 token 无效则返回 None
        """
        ...


class UserAuth(AuthProvider):
    """
    用户认证协议 - 用于本地模式

    支持用户注册、登录等操作。
    """

    async def register_user(self, username: str, password: str, **kwargs) -> bool:
        """
        注册新用户

        Args:
            username: 用户名
            password: 密码
            **kwargs: 其他注册信息（如 email, display_name 等）

        Returns:
            是否注册成功
        """
        ...

    async def authenticate_user(self, username: str, password: str) -> Optional[UserInfo]:
        """
        用户登录认证

        Args:
            username: 用户名
            password: 密码

        Returns:
            用户信息，如果认证失败则返回 None
        """
        ...

