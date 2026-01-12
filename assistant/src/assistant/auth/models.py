"""
用户认证相关的数据模型

定义用户和会话协作者实体
"""

from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class UserRole(str, Enum):
    """用户角色枚举"""
    GUEST = "guest"       # 访客：只读权限
    USER = "user"         # 普通用户：标准权限
    ADMIN = "admin"       # 管理员：完全权限


class User(BaseModel):
    """
    用户实体模型

    Args:
        id: 用户 ID（主键）
        username: 用户名（唯一）
        email: 邮箱地址（唯一）
        password_hash: 密码哈希
        display_name: 显示名称
        role: 用户角色
        is_active: 是否激活
        created_at: 创建时间（Unix timestamp）
        updated_at: 更新时间（Unix timestamp）
    """
    id: str = Field(..., description="用户 ID")
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[str] = Field(None, max_length=100, description="邮箱地址")
    password_hash: Optional[str] = Field(None, description="密码哈希")
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")
    role: UserRole = Field(default=UserRole.USER, description="用户角色")
    is_active: bool = Field(default=True, description="是否激活")
    created_at: float = Field(default=0, description="创建时间（Unix timestamp）")
    updated_at: float = Field(default=0, description="更新时间（Unix timestamp）")


class AuthUser(BaseModel):
    """
    认证用户信息（轻量级，用于 API 返回）

    Args:
        id: 用户 ID
        username: 用户名
        email: 邮箱
        display_name: 显示名称
        role: 用户角色
        is_active: 是否激活
    """
    id: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True

    @property
    def is_admin(self) -> bool:
        """检查是否是管理员"""
        return self.role == UserRole.ADMIN

    @property
    def can_write(self) -> bool:
        """检查是否有写入权限"""
        return self.role in [UserRole.USER, UserRole.ADMIN]


class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=6)
    display_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = Field(default=UserRole.USER)


class UpdateUserRequest(BaseModel):
    """更新用户请求"""
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[UserRole] = None


class Permission(str, Enum):
    """权限级别枚举"""
    READ = "read"         # 只读权限
    WRITE = "write"       # 读写权限
    ADMIN = "admin"       # 管理权限
