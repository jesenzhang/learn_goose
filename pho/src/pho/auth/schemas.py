"""
用户认证相关的 API Schema 和 DTO

定义用于 API 请求/响应的数据传输对象
"""

from typing import Optional
from pydantic import BaseModel, Field, EmailStr

from .models import UserRole


class Permission(str):
    """权限级别枚举"""
    READ = "read"         # 只读权限
    WRITE = "write"       # 读写权限
    ADMIN = "admin"       # 管理权限


class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=6)  # 可选，支持外部认证
    display_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = Field(default=UserRole.USER)


class UpdateUserRequest(BaseModel):
    """更新用户请求"""
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    role: Optional[UserRole] = None


class AuthUser(BaseModel):
    """
    认证用户信息（轻量级，用于 API 返回）

    不包含敏感信息（如密码哈希）
    """
    id: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True

    def has_permission(self, required_permission: Permission) -> bool:
        """
        检查用户是否有指定权限

        Args:
            required_permission: 需要的权限级别

        Returns:
            是否有权限
        """
        role_permissions = {
            UserRole.GUEST: [Permission.READ],
            UserRole.USER: [Permission.READ, Permission.WRITE],
            UserRole.ADMIN: [Permission.READ, Permission.WRITE, Permission.ADMIN],
        }

        user_permissions = role_permissions.get(self.role, [])
        return required_permission in user_permissions

    def can_write(self) -> bool:
        """检查是否有写入权限"""
        return self.has_permission(Permission.WRITE)

    def is_admin(self) -> bool:
        """检查是否是管理员"""
        return self.role == UserRole.ADMIN


def to_auth_user(user) -> AuthUser:
    """
    将 User 模型转换为 AuthUser（不包含敏感信息）

    Args:
        user: User 实例

    Returns:
        AuthUser 实例
    """
    return AuthUser(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active
    )
