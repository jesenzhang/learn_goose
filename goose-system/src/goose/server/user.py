"""
User Management Module

用户管理功能：
- 用户注册/登录
- 用户认证
- 用户会话关联
- JSONL 持久化存储

Reference: goose-rs/crates/goose-server/src/user.rs
"""

import json
import logging
import hashlib
import secrets
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
import asyncio
from enum import Enum

logger = logging.getLogger("goose.server.user")


class UserRole(str, Enum):
    """用户角色"""
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


@dataclass
class User:
    """用户模型"""
    user_id: str
    username: str
    password_hash: str
    email: Optional[str] = None
    role: UserRole = UserRole.USER
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_password: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }
        if include_password:
            result["password_hash"] = self.password_hash
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """从字典创建"""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            email=data.get("email"),
            password_hash=data["password_hash"],
            role=UserRole(data.get("role", "user")),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {})
        )

    def verify_password(self, password: str) -> bool:
        """验证密码"""
        return self.password_hash == User.hash_password(password)

    @staticmethod
    def hash_password(password: str) -> str:
        """哈希密码"""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def generate_user_id() -> str:
        """生成用户 ID"""
        import uuid
        return str(uuid.uuid4())


@dataclass
class Session:
    """用户会话模型"""
    session_id: str
    user_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now().timestamp() + 3600 * 24).__class__())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at", (datetime.now().timestamp() + 3600 * 24).__class__()),
            metadata=data.get("metadata", {})
        )

    def is_expired(self) -> bool:
        """检查会话是否过期"""
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except Exception:
            return True

    @staticmethod
    def generate_session_id() -> str:
        """生成会话 ID"""
        import uuid
        return str(uuid.uuid4())


class UserStorageBackend:
    """用户存储后端抽象"""

    async def get_user(self, user_id: str) -> Optional[User]:
        pass

    async def get_user_by_username(self, username: str) -> Optional[User]:
        pass

    async def get_user_by_email(self, email: str) -> Optional[User]:
        pass

    async def create_user(self, user: User) -> bool:
        pass

    async def update_user(self, user: User) -> bool:
        pass

    async def delete_user(self, user_id: str) -> bool:
        pass

    async def list_users(self, limit: int = 100) -> List[User]:
        pass

    async def create_session(self, session: Session) -> bool:
        pass

    async def get_session(self, session_id: str) -> Optional[Session]:
        pass

    async def get_user_sessions(self, user_id: str) -> List[Session]:
        pass

    async def delete_session(self, session_id: str) -> bool:
        pass

    async def cleanup_expired_sessions(self) -> int:
        pass


class JsonLUserStorage(UserStorageBackend):
    """基于 JSONL 的用户存储后端"""

    def __init__(self, storage_dir: str = "./data/users"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        users_file = self.storage_dir / "users.jsonl"
        sessions_file = self.storage_dir / "sessions.jsonl"

        self.users_file = users_file
        self.sessions_file = sessions_file
        self._lock = asyncio.Lock()

    def _load_jsonl(self, file_path: Path) -> List[Dict[str, Any]]:
        """加载 JSONL 文件"""
        if not file_path.exists():
            return []

        try:
            results = []
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            results.append(json.loads(line))
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in {file_path}")
            return results
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return []

    def _append_jsonl(self, file_path: Path, data: Dict[str, Any]) -> None:
        """追加到 JSONL 文件"""
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error writing to {file_path}: {e}")
            raise

    def _rewrite_jsonl(self, file_path: Path, data_list: List[Dict[str, Any]]) -> None:
        """重写 JSONL 文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for data in data_list:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error writing to {file_path}: {e}")
            raise

    def _delete_from_jsonl(self, file_path: Path, key: str, key_field: str) -> bool:
        """从 JSONL 文件删除条目"""
        data_list = self._load_jsonl(file_path)
        original_len = len(data_list)
        data_list = [d for d in data_list if d.get(key_field) != key]

        if len(data_list) == original_len:
            return False

        self._rewrite_jsonl(file_path, data_list)
        return True

    async def get_user(self, user_id: str) -> Optional[User]:
        async with self._lock:
            users = self._load_jsonl(self.users_file)
            for user_data in users:
                if user_data.get("user_id") == user_id:
                    return User.from_dict(user_data)
            return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        async with self._lock:
            users = self._load_jsonl(self.users_file)
            for user_data in users:
                if user_data.get("username") == username:
                    return User.from_dict(user_data)
            return None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        async with self._lock:
            users = self._load_jsonl(self.users_file)
            for user_data in users:
                if user_data.get("email") == email:
                    return User.from_dict(user_data)
            return None

    async def create_user(self, user: User) -> bool:
        async with self._lock:
            # 检查用户名是否已存在
            existing = await self.get_user_by_username(user.username)
            if existing:
                logger.warning(f"Username {user.username} already exists")
                return False

            # 如果有邮箱，检查邮箱是否已存在
            if user.email:
                existing_email = await self.get_user_by_email(user.email)
                if existing_email:
                    logger.warning(f"Email {user.email} already exists")
                    return False

            self._append_jsonl(self.users_file, user.to_dict(include_password=True))
            logger.info(f"Created user: {user.user_id}")
            return True

    async def update_user(self, user: User) -> bool:
        async with self._lock:
            # 删除旧记录
            self._delete_from_jsonl(self.users_file, user.user_id, "user_id")

            # 添加新记录
            self._append_jsonl(self.users_file, user.to_dict(include_password=True))
            return True

    async def delete_user(self, user_id: str) -> bool:
        async with self._lock:
            # 删除用户
            deleted = self._delete_from_jsonl(self.users_file, user_id, "user_id")

            if deleted:
                # 删除用户的所有会话
                sessions = self._load_jsonl(self.sessions_file)
                user_sessions = [s for s in sessions if s.get("user_id") == user_id]

                for session in user_sessions:
                    await self.delete_session(session["session_id"])

            return deleted

    async def list_users(self, limit: int = 100) -> List[User]:
        async with self._lock:
            users = self._load_jsonl(self.users_file)
            return [User.from_dict(u) for u in users[:limit]]

    async def create_session(self, session: Session) -> bool:
        async with self._lock:
            # 检查用户是否存在
            user = await self.get_user(session.user_id)
            if not user:
                logger.warning(f"User {session.user_id} not found")
                return False

            self._append_jsonl(self.sessions_file, session.to_dict())
            logger.info(f"Created session: {session.session_id}")
            return True

    async def get_session(self, session_id: str) -> Optional[Session]:
        async with self._lock:
            sessions = self._load_jsonl(self.sessions_file)
            for session_data in sessions:
                if session_data.get("session_id") == session_id:
                    return Session.from_dict(session_data)
            return None

    async def get_user_sessions(self, user_id: str) -> List[Session]:
        async with self._lock:
            sessions = self._load_jsonl(self.sessions_file)
            result = []
            for session_data in sessions:
                if session_data.get("user_id") == user_id:
                    session = Session.from_dict(session_data)
                    if not session.is_expired():
                        result.append(session)
            return result

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            return self._delete_from_jsonl(self.sessions_file, session_id, "session_id")

    async def cleanup_expired_sessions(self) -> int:
        async with self._lock:
            sessions = self._load_jsonl(self.sessions_file)
            original_len = len(sessions)

            # 过滤掉过期会话
            valid_sessions = []
            for session_data in sessions:
                session = Session.from_dict(session_data)
                if not session.is_expired():
                    valid_sessions.append(session_data)

            if len(valid_sessions) == original_len:
                return 0

            self._rewrite_jsonl(self.sessions_file, valid_sessions)
            expired_count = original_len - len(valid_sessions)
            logger.info(f"Cleaned up {expired_count} expired sessions")
            return expired_count


class UserManager:
    """
    用户管理器

    功能：
    - 用户注册/登录
    - 会话管理
    - 用户认证
    """

    _instance: Optional["UserManager"] = None
    _lock = asyncio.Lock()

    def __init__(self, storage: Optional[UserStorageBackend] = None):
        self.storage = storage or JsonLUserStorage()
        self._session_cache: Dict[str, Session] = {}

    @classmethod
    async def instance(cls) -> "UserManager":
        """获取全局单例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = UserManager()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "UserManager") -> None:
        """设置全局实例（用于测试）"""
        cls._instance = instance

    async def register_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        role: UserRole = UserRole.USER
    ) -> tuple[bool, Optional[User], Optional[str]]:
        """
        注册用户

        Returns:
            (success, user, error_message)
        """
        # 验证用户名
        if not username or len(username) < 3:
            return False, None, "Username must be at least 3 characters"

        if len(username) > 50:
            return False, None, "Username must be less than 50 characters"

        # 验证密码
        if not password or len(password) < 6:
            return False, None, "Password must be at least 6 characters"

        # 验证邮箱格式
        if email:
            if "@" not in email or "." not in email.split("@")[-1]:
                return False, None, "Invalid email format"

        # 检查用户名是否已存在
        existing = await self.storage.get_user_by_username(username)
        if existing:
            return False, None, "Username already exists"

        # 检查邮箱是否已存在
        if email:
            existing_email = await self.storage.get_user_by_email(email)
            if existing_email:
                return False, None, "Email already exists"

        # 创建用户
        user = User(
            user_id=User.generate_user_id(),
            username=username,
            email=email,
            password_hash=User.hash_password(password),
            role=role
        )

        success = await self.storage.create_user(user)
        if success:
            logger.info(f"User registered: {username}")
            return True, user, None
        return False, None, "Failed to create user"

    async def login_user(
        self,
        username: str,
        password: str,
        expire_hours: int = 24
    ) -> tuple[bool, Optional[Session], Optional[str]]:
        """
        用户登录

        Returns:
            (success, session, error_message)
        """
        # 获取用户
        user = await self.storage.get_user_by_username(username)
        if not user:
            return False, None, "User not found"

        # 验证密码
        if not user.verify_password(password):
            return False, None, "Invalid password"

        if not user.is_active:
            return False, None, "User account is inactive"

        # 创建会话
        import time
        session = Session(
            session_id=Session.generate_session_id(),
            user_id=user.user_id,
            expires_at=datetime.fromtimestamp(time.time() + expire_hours * 3600).isoformat()
        )

        success = await self.storage.create_session(session)
        if success:
            self._session_cache[session.session_id] = session
            logger.info(f"User logged in: {username}")
            return True, session, None

        return False, None, "Failed to create session"

    async def logout_user(self, session_id: str) -> bool:
        """用户登出"""
        if session_id in self._session_cache:
            del self._session_cache[session_id]

        return await self.storage.delete_session(session_id)

    async def get_user_from_session(self, session_id: str) -> Optional[User]:
        """从会话获取用户"""
        # 先检查缓存
        if session_id in self._session_cache:
            session = self._session_cache[session_id]
            if session.is_expired():
                del self._session_cache[session_id]
                await self.storage.delete_session(session_id)
                return None

            user = await self.storage.get_user(session.user_id)
            return user

        # 从存储加载
        session = await self.storage.get_session(session_id)
        if not session:
            return None

        if session.is_expired():
            await self.storage.delete_session(session_id)
            return None

        self._session_cache[session_id] = session
        return await self.storage.get_user(session.user_id)

    async def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return await self.storage.get_user(user_id)

    async def update_user(
        self,
        user_id: str,
        **updates
    ) -> tuple[bool, Optional[User], Optional[str]]:
        """
        更新用户

        Returns:
            (success, user, error_message)
        """
        user = await self.storage.get_user(user_id)
        if not user:
            return False, None, "User not found"

        # 应用更新
        if "email" in updates:
            user.email = updates["email"]
        if "role" in updates:
            user.role = UserRole(updates["role"])
        if "is_active" in updates:
            user.is_active = updates["is_active"]
        if "metadata" in updates:
            user.metadata = {**user.metadata, **updates["metadata"]}

        # 不允许直接更新密码
        if "password" in updates:
            user.password_hash = User.hash_password(updates["password"])

        user.updated_at = datetime.now().isoformat()

        success = await self.storage.update_user(user)
        if success:
            return True, user, None
        return False, None, "Failed to update user"

    async def list_users(self, limit: int = 100) -> List[User]:
        """列出用户"""
        return await self.storage.list_users(limit)

    async def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        return await self.storage.delete_user(user_id)

    async def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        # 清理缓存
        expired_sessions = [
            sid for sid, session in self._session_cache.items()
            if session.is_expired()
        ]
        for sid in expired_sessions:
            del self._session_cache[sid]

        # 清理存储
        return await self.storage.cleanup_expired_sessions()

    async def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> tuple[bool, Optional[str]]:
        """
        修改密码

        Returns:
            (success, error_message)
        """
        user = await self.storage.get_user(user_id)
        if not user:
            return False, "User not found"

        if not user.verify_password(old_password):
            return False, "Invalid old password"

        if len(new_password) < 6:
            return False, "New password must be at least 6 characters"

        user.password_hash = User.hash_password(new_password)
        user.updated_at = datetime.now().isoformat()

        success = await self.storage.update_user(user)
        if success:
            logger.info(f"Password changed for user: {user_id}")
            return True, None
        return False, "Failed to update password"


# 便捷函数

async def get_user_manager() -> UserManager:
    """获取全局用户管理器"""
    return await UserManager.instance()
