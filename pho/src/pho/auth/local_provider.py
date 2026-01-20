"""
Local Auth Provider - 本地认证提供者

使用 assistant 内置数据库进行用户认证和会话管理。
"""

import logging
import asyncio
import json
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

from .protocol import AuthProvider, UserAuth, UserInfo, AuthConfig
from ..db import AsyncDatabaseManager
from ..db.protocol import MemoryProtocol

logger = logging.getLogger(__name__)


class LocalAuthProvider:
    """
    本地认证提供者

    使用内置 SQLite 数据库进行用户管理。
    """

    def __init__(self, config: AuthConfig, db_manager: Optional[AsyncDatabaseManager] = None):
        """
        初始化本地认证提供者

        Args:
            config: 认证配置
            db_manager: 数据库管理器（可选，如果不提供则创建一个）
        """
        self.config = config
        self._db: Optional[AsyncDatabaseManager] = db_manager
        self._initialized = False

    async def initialize(self) -> bool:
        """初始化认证提供者"""
        if self._initialized:
            return True

        try:
            # 如果没有提供 db_manager，创建一个
            if self._db is None:
                self._db = AsyncDatabaseManager(db_path=self.config.local_db_path)
                await self._db.initialize()

            # 确保 users 表存在
            await self._ensure_users_table()

            self._initialized = True
            logger.info("LocalAuthProvider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize LocalAuthProvider: {e}", exc_info=e)
            return False

    async def _ensure_users_table(self):
        """确保 users 表存在"""
        async with self._db._get_connection() as conn:
            # 检查表是否存在
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            table_exists = await cursor.fetchone()

            if not table_exists:
                # 创建 users 表
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        display_name TEXT,
                        email TEXT,
                        permissions TEXT,
                        created_at TEXT NOT NULL,
                        last_active TEXT
                    )
                """)
                # 创建索引
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                logger.info("Created users table")
            else:
                # 检查并添加缺失的列
                await self._migrate_users_table(conn)

    async def _migrate_users_table(self, conn):
        """迁移 users 表结构（兼容旧版本）"""
        try:
            cursor = await conn.execute("PRAGMA table_info(users)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            # 检查并添加 permissions 列
            if 'permissions' not in column_names:
                await conn.execute("ALTER TABLE users ADD COLUMN permissions TEXT")
                logger.info("Added permissions column to users table")
        except Exception as e:
            logger.warning(f"Migration warning: {e}")

    async def close(self) -> None:
        """关闭认证提供者"""
        if self._db:
            await self._db.close()
        self._initialized = False
        logger.info("LocalAuthProvider closed")

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._initialized:
            return False

        try:
            async with self._db._get_connection() as conn:
                await conn.execute("SELECT 1 FROM users LIMIT 1")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=e)
            return False

    async def register_user(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        注册新用户

        Args:
            username: 用户名
            password: 密码
            display_name: 显示名称
            email: 邮箱
            **kwargs: 其他参数

        Returns:
            是否注册成功
        """
        if not self._initialized:
            logger.warning("AuthProvider not initialized")
            return False

        try:
            # 检查用户名是否已存在
            async with self._db._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT user_id FROM users WHERE username = ?",
                    (username,)
                )
                existing = await cursor.fetchone()

                if existing:
                    logger.warning(f"Username already exists: {username}")
                    return False

                # 密码哈希
                password_hash = self._hash_password(password)

                # 生成 user_id
                user_id = self._generate_user_id(username)

                # 插入用户记录
                now = datetime.now().isoformat()
                permissions_json = json.dumps(kwargs.get('permissions', {}))

                await conn.execute("""
                    INSERT INTO users (user_id, username, password_hash, display_name, email, permissions, created_at, last_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, username, password_hash,
                    display_name or username,
                    email,
                    permissions_json,
                    now, now
                ))

                logger.info(f"User registered: {username} ({user_id})")
                return True
        except Exception as e:
            logger.error(f"Failed to register user: {e}", exc_info=e)
            return False

    async def authenticate_user(
        self,
        username: str,
        password: str
    ) -> Optional[UserInfo]:
        """
        用户登录认证

        Args:
            username: 用户名
            password: 密码

        Returns:
            用户信息，如果认证失败则返回 None
        """
        if not self._initialized:
            logger.warning("AuthProvider not initialized")
            return None

        try:
            async with self._db._get_connection() as conn:
                # 查询用户
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE username = ?",
                    (username,)
                )
                row = await cursor.fetchone()

                if not row:
                    logger.debug(f"User not found: {username}")
                    return None

                # 验证密码
                password_hash = self._hash_password(password)
                stored_hash = row[2]  # password_hash 列

                if password_hash != stored_hash:
                    logger.debug(f"Invalid password for user: {username}")
                    return None

                # 更新最后活跃时间
                now = datetime.now().isoformat()
                await conn.execute(
                    "UPDATE users SET last_active = ? WHERE user_id = ?",
                    (now, row[0])  # user_id 列
                )

                # 返回用户信息
                permissions = json.loads(row[5]) if row[5] else {}

                return UserInfo(
                    user_id=row[0],
                    username=row[1],
                    display_name=row[3] or username,
                    email=row[4],
                    permissions=permissions,
                    created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    last_active=datetime.now(),
                    metadata={}
                )
        except Exception as e:
            logger.error(f"Failed to authenticate user: {e}", exc_info=e)
            return None

    def _hash_password(self, password: str) -> str:
        """
        密码哈希（使用 SHA-256 + salt）

        实际生产环境中建议使用 bcrypt 或 argon2
        """
        salt = "assistant_local_auth_salt"  # 应该从配置读取
        salted = password + salt
        return hashlib.sha256(salted.encode()).hexdigest()

    def _generate_user_id(self, username: str) -> str:
        """
        生成用户 ID

        Args:
            username: 用户名

        Returns:
            用户 ID
        """
        # 简单实现：使用用户名
        return f"user_{username}"

    async def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        """
        获取用户信息

        Args:
            user_id: 用户 ID

        Returns:
            用户信息，如果不存在则返回 None
        """
        if not self._initialized:
            return None

        try:
            async with self._db._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                permissions = json.loads(row[5]) if row[5] else {}

                return UserInfo(
                    user_id=row[0],
                    username=row[1],
                    display_name=row[3] or row[1],
                    email=row[4],
                    permissions=permissions,
                    created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    last_active=datetime.fromisoformat(row[7]) if row[7] else None,
                    metadata={}
                )
        except Exception as e:
            logger.error(f"Failed to get user info: {e}", exc_info=e)
            return None

    async def list_users(self, limit: int = 100) -> list[UserInfo]:
        """
        列出所有用户

        Args:
            limit: 返回数量限制

        Returns:
            用户列表
        """
        if not self._initialized:
            return []

        try:
            async with self._db._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                rows = await cursor.fetchall()

                users = []
                for row in rows:
                    permissions = json.loads(row[5]) if row[5] else {}

                    users.append(UserInfo(
                        user_id=row[0],
                        username=row[1],
                        display_name=row[3] or row[1],
                        email=row[4],
                        permissions=permissions,
                        created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                        last_active=datetime.fromisoformat(row[7]) if row[7] else None,
                        metadata={}
                    ))

                return users
        except Exception as e:
            logger.error(f"Failed to list users: {e}", exc_info=e)
            return []

    async def delete_user(self, user_id: str) -> bool:
        """
        删除用户

        Args:
            user_id: 用户 ID

        Returns:
            是否删除成功
        """
        if not self._initialized:
            return False

        try:
            async with self._db._get_connection() as conn:
                await conn.execute(
                    "DELETE FROM users WHERE user_id = ?",
                    (user_id,)
                )
                logger.info(f"Deleted user: {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete user: {e}", exc_info=e)
            return False
