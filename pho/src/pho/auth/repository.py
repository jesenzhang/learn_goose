"""
用户认证相关的数据仓储

独立定义 users 和 session_collaborators 表，与 session 模块解耦
"""

import logging
import time
import uuid
import hashlib
from typing import List, Optional

from ..persistence import BaseRepository, with_table
from .models import User, SessionCollaborator, UserRole

logger = logging.getLogger("pho.auth.repository")


# ==================== SQL Schema 定义 ====================

# 用户表
USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);
"""

# 用户名唯一索引
USERS_INDEX_USERNAME = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);
"""

# 邮箱唯一索引
USERS_INDEX_EMAIL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""

# 用户角色索引
USERS_INDEX_ROLE = """
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
"""

# 会话协作者表
SESSION_COLLABORATORS_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_collaborators (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    added_at REAL NOT NULL DEFAULT 0,
    added_by TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# 会话协作者复合索引（快速查找某个会话的所有协作者）
SESSION_COLLABORATORS_INDEX_SESSION = """
CREATE INDEX IF NOT EXISTS idx_session_collaborators_session
ON session_collaborators(session_id);
"""

# 会话协作者复合索引（快速查找某个用户参与的所有会话）
SESSION_COLLABORATORS_INDEX_USER = """
CREATE INDEX IF NOT EXISTS idx_session_collaborators_user
ON session_collaborators(user_id);
"""

# 唯一约束：一个用户在一个会话中只能有一个记录
SESSION_COLLABORATORS_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_collaborators_unique
ON session_collaborators(session_id, user_id);
"""


# ==================== Repository 定义 ====================

@with_table(
    name='users',
    model=User,
    sql=[USERS_SCHEMA, USERS_INDEX_USERNAME, USERS_INDEX_EMAIL, USERS_INDEX_ROLE],
    pk='id',
    priority=-10,
    attr_name='user_spec'
)
class UserRepository(BaseRepository):
    """
    用户仓储接口

    独立管理 users 表，与 SessionRepository 解耦
    """

    async def create_user(
        self,
        username: str,
        password: Optional[str] = None,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        role: UserRole = UserRole.USER
    ) -> User:
        """
        创建新用户

        Args:
            username: 用户名
            password: 密码（可选，支持外部认证）
            email: 邮箱
            display_name: 显示名称
            role: 用户角色

        Returns:
            创建的用户对象

        Raises:
            ValueError: 用户名或邮箱已存在
        """
        # 检查用户名是否已存在
        existing = await self._find(User, {"username": username}, limit=1)
        if existing:
            raise ValueError(f"Username '{username}' already exists")

        # 检查邮箱是否已存在
        if email:
            existing_email = await self._find(User, {"email": email}, limit=1)
            if existing_email:
                raise ValueError(f"Email '{email}' already exists")

        # 生成密码哈希
        password_hash = None
        if password:
            password_hash = self._hash_password(password)

        now = time.time()
        user = User(
            id=uuid.uuid4().hex,
            username=username,
            email=email,
            password_hash=password_hash,
            display_name=display_name or username,
            role=role,
            is_active=True,
            created_at=now,
            updated_at=now
        )

        await self._insert(User, user)
        logger.info(f"Created user: {user.id} ({username})")
        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据用户 ID 获取用户"""
        try:
            return await self._get(User, user_id)
        except Exception:
            return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        results = await self._find(User, {"username": username}, limit=1)
        return results[0] if results else None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        if not email:
            return None
        results = await self._find(User, {"email": email}, limit=1)
        return results[0] if results else None

    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[User]:
        """列出所有用户"""
        return await self._find(User, {}, limit=limit, offset=offset)

    async def count_users(self) -> int:
        """获取用户总数"""
        return await self._count(User, {})

    async def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        role: Optional[UserRole] = None
    ) -> Optional[User]:
        """
        更新用户信息

        Args:
            user_id: 用户 ID
            email: 新邮箱
            display_name: 新显示名称
            role: 新角色

        Returns:
            更新后的用户对象
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        # 构建更新数据
        update_data = {"updated_at": time.time()}
        if email is not None:
            # 检查邮箱是否被其他用户使用
            existing = await self._find(User, {"email": email}, limit=1)
            if existing and existing[0].id != user_id:
                raise ValueError(f"Email '{email}' already exists")
            update_data["email"] = email

        if display_name is not None:
            update_data["display_name"] = display_name

        if role is not None:
            update_data["role"] = role

        await self._update_by(User, {"id": user_id}, **update_data)

        # 返回更新后的用户
        return await self.get_user_by_id(user_id)

    async def update_user_role(
        self,
        user_id: str,
        new_role: UserRole
    ) -> Optional[User]:
        """更新用户角色"""
        await self._update_by(
            User,
            {"id": user_id},
            role=new_role.value,
            updated_at=time.time()
        )
        logger.info(f"Updated user {user_id} role to {new_role}")
        return await self.get_user_by_id(user_id)

    async def deactivate_user(self, user_id: str) -> bool:
        """停用用户"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        await self._update_by(
            User,
            {"id": user_id},
            is_active=False,
            updated_at=time.time()
        )
        logger.info(f"Deactivated user {user_id}")
        return True

    async def activate_user(self, user_id: str) -> bool:
        """激活用户"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        await self._update_by(
            User,
            {"id": user_id},
            is_active=True,
            updated_at=time.time()
        )
        logger.info(f"Activated user {user_id}")
        return True

    async def verify_password(self, user_id: str, password: str) -> bool:
        """
        验证用户密码

        Args:
            user_id: 用户 ID
            password: 明文密码

        Returns:
            密码是否正确
        """
        user = await self.get_user_by_id(user_id)
        if not user or not user.password_hash:
            return False

        return user.password_hash == self._hash_password(password)

    async def change_password(self, user_id: str, new_password: str) -> bool:
        """
        修改用户密码

        Args:
            user_id: 用户 ID
            new_password: 新密码

        Returns:
            是否修改成功
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return False

        await self._update_by(
            User,
            {"id": user_id},
            password_hash=self._hash_password(new_password),
            updated_at=time.time()
        )
        logger.info(f"Changed password for user {user_id}")
        return True

    def _hash_password(self, password: str) -> str:
        """
        密码哈希（简化实现）

        生产环境应该使用 bcrypt 或 argon2
        """
        return hashlib.sha256(password.encode()).hexdigest()


@with_table(
    name='session_collaborators',
    model=SessionCollaborator,
    sql=[
        SESSION_COLLABORATORS_SCHEMA,
        SESSION_COLLABORATORS_INDEX_SESSION,
        SESSION_COLLABORATORS_INDEX_USER,
        SESSION_COLLABORATORS_UNIQUE
    ],
    pk='id',
    priority=0,
    attr_name='collaborator_spec'
)
class SessionCollaboratorRepository(BaseRepository):
    """
    会话协作者仓储接口

    独立管理 session_collaborators 表
    """

    async def add_collaborator(
        self,
        session_id: str,
        user_id: str,
        role: str = "viewer",
        added_by: Optional[str] = None
    ) -> SessionCollaborator:
        """
        添加协作者到会话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            role: 角色
            added_by: 添加者用户 ID

        Returns:
            创建的协作者对象
        """
        # 检查是否已经是协作者
        existing = await self._find(
            SessionCollaborator,
            {"session_id": session_id, "user_id": user_id},
            limit=1
        )
        if existing:
            # 更新角色
            await self._update_by(
                SessionCollaborator,
                {"session_id": session_id, "user_id": user_id},
                role=role,
                added_at=time.time()
            )
            results = await self._find(
                SessionCollaborator,
                {"session_id": session_id, "user_id": user_id},
                limit=1
            )
            return results[0]

        collaborator = SessionCollaborator(
            id=uuid.uuid4().hex,
            session_id=session_id,
            user_id=user_id,
            role=role,
            added_at=time.time(),
            added_by=added_by
        )

        await self._insert(SessionCollaborator, collaborator)
        logger.info(f"Added user {user_id} as collaborator to session {session_id}")
        return collaborator

    async def remove_collaborator(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """
        从会话移除协作者

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            是否移除成功
        """
        count = await self._delete_by(
            SessionCollaborator,
            {"session_id": session_id, "user_id": user_id}
        )
        logger.info(f"Removed collaborator {user_id} from session {session_id}")
        return count > 0

    async def list_collaborators(
        self,
        session_id: str
    ) -> List[SessionCollaborator]:
        """
        列出会话的协作者

        Args:
            session_id: 会话 ID

        Returns:
            协作者列表
        """
        return await self._find(
            SessionCollaborator,
            {"session_id": session_id}
        )

    async def get_collaborator_sessions(
        self,
        user_id: str
    ) -> List[SessionCollaborator]:
        """
        获取用户参与的所有协作会话

        Args:
            user_id: 用户 ID

        Returns:
            协作会话列表
        """
        return await self._find(
            SessionCollaborator,
            {"user_id": user_id}
        )

    async def is_collaborator(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """
        检查用户是否是会话的协作者

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            是否是协作者
        """
        results = await self._find(
            SessionCollaborator,
            {"session_id": session_id, "user_id": user_id},
            limit=1
        )
        return len(results) > 0

    async def get_collaborator_role(
        self,
        session_id: str,
        user_id: str
    ) -> Optional[str]:
        """
        获取协作者的角色

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            协作者角色，如果不是协作者则返回 None
        """
        results = await self._find(
            SessionCollaborator,
            {"session_id": session_id, "user_id": user_id},
            limit=1
        )
        return results[0].role if results else None
