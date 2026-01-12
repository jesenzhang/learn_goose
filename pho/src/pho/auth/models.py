"""
用户认证相关的数据模型

定义 User 和 SessionCollaborator 实体，支持持久化存储
"""

from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class UserRole(str, Enum):
    """用户角色枚举"""
    GUEST = "guest"       # 访客：只读权限
    USER = "user"         # 普通用户：标准权限
    ADMIN = "admin"       # 管理员：完全权限


class CollaboratorRole(str, Enum):
    """协作者角色枚举"""
    VIEWER = "viewer"     # 只读访问
    EDITOR = "editor"     # 可编辑，不能删除
    OWNER = "owner"       # 完全控制（包括管理协作者）


class User(BaseModel):
    """
    用户实体模型

    Args:
        id: 用户 ID（主键）
        username: 用户名（唯一）
        email: 邮箱地址（唯一）
        password_hash: 密码哈希（可选，支持外部认证）
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


class SessionCollaborator(BaseModel):
    """
    会话协作者关联实体模型

    Args:
        id: 关联 ID（主键）
        session_id: 会话 ID
        user_id: 用户 ID
        role: 协作者角色（存储为字符串）
        added_at: 添加时间（Unix timestamp）
        added_by: 添加者用户 ID
    """
    id: str = Field(..., description="关联 ID")
    session_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    role: str = Field(default="viewer", description="协作者角色")
    added_at: float = Field(default=0, description="添加时间（Unix timestamp）")
    added_by: Optional[str] = Field(None, description="添加者用户 ID")
