import json
from goose.persistence import BaseRepository,with_table,TableSpec
from typing import Optional,Dict,Any,List
import time
from passlib.context import CryptContext
from .types import User,ResourceType,UserResourceBinding,UserSession
import logging
import uuid
import hashlib
import secrets


def hash_password(password: str) -> str:
    """使用hashlib和随机盐值对密码进行哈希处理"""
    salt = secrets.token_hex(32)  # 生成随机盐值
    pwdhash = hashlib.pbkdf2_hmac('sha256',
                                  password.encode('utf-8'),
                                  salt.encode('ascii'),
                                  100000)  # 使用100000次迭代
    return salt + pwdhash.hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码是否匹配哈希值"""
    if len(hashed_password) < 64:
        return False  # 哈希值太短，无效
    
    salt = hashed_password[:64]  # 提取前64字符作为盐值（32字节hex）
    stored_hash = hashed_password[64:]  # 提取剩余部分作为哈希值
    
    # 用同样的方式对明文密码进行哈希
    pwdhash = hashlib.pbkdf2_hmac('sha256',
                                  plain_password.encode('utf-8'),
                                  salt.encode('ascii'),
                                  100000)
    return pwdhash.hex() == stored_hash

logger = logging.getLogger("goose.app.user.repo")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# 新增 User Schema
USER_SCHEMA = ["""
    CREATE TABLE IF NOT EXISTS users (
        -- [核心身份]
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,      -- 用于显示和提及
        email TEXT UNIQUE,                  -- 用于登录和找回密码 (可选，建议有)
        phone TEXT UNIQUE,                  -- 手机号 (可选)

        -- [安全凭证]
        hashed_password TEXT,               -- 🚨 绝对禁止存明文密码！存放 bcrypt/argon2 哈希值
        api_key TEXT,                       -- 用于 Agent/API 调用 (建议存 Hash，开发环境可明文)
        
        -- [基础信息]
        nickname TEXT,                      -- 显示名称 (如 "Goose 开发者")
        avatar_url TEXT,                    -- 头像链接
        
        -- [状态与权限]
        is_active INTEGER DEFAULT 1,        -- Boolean: 软删除或封禁使用
        is_superuser INTEGER DEFAULT 0,     -- Boolean: 超级管理员权限
        roles TEXT,                         -- JSON List: ["editor", "viewer"] 简单的 RBAC
        
        -- [扩展配置 - 避免频繁加列]
        profile TEXT,                       -- JSON: 用户的公开资料 (bio, social_links)
        settings TEXT,                      -- JSON: 用户的私有偏好 (theme, language, notification)
        
        -- [审计时间 - 使用 REAL 存 Unix Timestamp]
        last_login_at REAL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
    "CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);"
]


USER_SESSION_SCHEMA = ["""
    CREATE TABLE IF NOT EXISTS user_sessions (
        id TEXT PRIMARY KEY,          -- Session ID (也是 Refresh Token 的唯一标识 JTI)
        user_id TEXT NOT NULL,        -- 归属用户
        
        refresh_token_hash TEXT NOT NULL, -- Refresh Token 的哈希值 (安全存放)
        
        user_agent TEXT,              -- 设备信息 (如 "Mozilla/5.0... iPhone")
        ip_address TEXT,              -- IP 地址
        
        is_valid INTEGER DEFAULT 1,   -- 是否有效 (用于软登出)
        expires_at REAL NOT NULL,     -- 过期时间 (Unix Timestamp)
        created_at REAL,
        last_used_at REAL,            -- 最后活跃时间
        
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(refresh_token_hash);"
]


@with_table(name ='users',model=User,sql=USER_SCHEMA,priority=0,pk='id',attr_name='user_spec')
@with_table(name ='user_sessions',model=UserSession,sql=USER_SESSION_SCHEMA,priority=1,pk='id',attr_name='user_session_spec')
class UserRepository(BaseRepository):
     # --- 1. 基础流程 (Dev Mode) ---
    async def create_user(self, username: str, password: str, **kwargs) -> User:
        # 1. 哈希密码
        hashed = hash_password(password)
        
        # 2. 创建对象
        user = User(
            username=username,
            hashed_password=hashed,
            **kwargs
        )
        
        await self._insert(User, user)
        return user
    
    async def get_by_id(self, user_id: str) -> Optional[Dict]:
        return await self._get(User,user_id)
    
    async def get_by_username(self, username: str) -> Optional[User]:
        users = await self._find(User,filter={
            "username": username
        })
        if users:
            return users[0]
    
    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """验证用户名密码"""
        # 1. 查用户
        user:User = await self.get_by_username(username)
        if not user:
            return None
            
        # 2. 验密码
        if not user.hashed_password:
            return None
            
        if verify_password(password, user.hashed_password):
            # (可选) 如果哈希算法升级了，这里可以重新 rehash 并更新
            return user
            
        return None
    
    # --- 2. 高级流程 (Dev Mode) ---
    async def update_field(self, user_id: str, **kwargs):
        """[Generic] 更新单个字段"""
        try:
            await self._update_by(User,filter={"id": user_id},**kwargs)
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")


    async def create_session(self, session: UserSession):
        await self._insert(UserSession, session)

    async def touch_session(self, session_id: str):
        """
        [Activity] 更新会话的最后活跃时间
        用于统计活跃度，或实现 '闲置30分钟自动退出' 的逻辑
        """
        await self._update_by(
            UserSession, 
            filters={"id": session_id}, 
            last_used_at=time.time()
        )
        
    async def get_active_session(self, session_id: str) -> Optional[UserSession]:
        """获取一个未过期的有效会话"""
        # 1. 查库
        sessions:List[UserSession] = await self._find(
            UserSession, 
            filters={"id": session_id, "is_valid": True}, 
            limit=1
        )
        if not sessions:
            return None
            
        session = sessions[0]
        
        # 2. 检查过期时间
        if session.expires_at < time.time():
            return None
            
        return session

    async def revoke_session(self, session_id: str):
        """[Logout] 注销单个会话"""
        await self._update_by(
            UserSession, 
            filters={"id": session_id}, 
            is_valid=False
        )

    async def revoke_all_user_sessions(self, user_id: str):
        """[Security] 踢该用户所有设备下线 (改密码时用)"""
        await self._update_by(
            UserSession, 
            filters={"user_id": user_id}, 
            is_valid=False
        )
        
        
USER_RESOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_resources (
    id TEXT PRIMARY KEY,          -- 改为 UUID，统一风格
    user_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,  -- 存字符串
    created_at REAL,              -- 改为 REAL
    
    -- 联合唯一索引：防止重复绑定
    UNIQUE(user_id, resource_id, resource_type)
);
"""

USER_RESOURCE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_ur_resource_id ON user_resources(resource_id);
CREATE INDEX IF NOT EXISTS idx_ur_user_type ON user_resources(user_id, resource_type);
"""

@with_table(name ='user_resources',model=UserResourceBinding,sql=[USER_RESOURCE_SCHEMA,USER_RESOURCE_INDEX],priority=2,pk='id',attr_name='user_resource_spec')
class UserResourceRepository(BaseRepository):
    """
    专门负责管理 User <-> Resource 的绑定关系
    """

    async def bind(self, user_id: str, resource_id: str, resource_type: ResourceType):
        """
        [Link] 绑定资源给用户
        """
        try:
            # 1. 先检查是否存在 (防止 UNIQUE 报错，且兼容 JSONL)
            exists = await self.check_ownership(user_id, resource_id)
            if exists:
                return

            # 2. 创建绑定对象
            binding = UserResourceBinding(
                user_id=user_id,
                resource_id=resource_id,
                resource_type=resource_type
            )
            
            # 3. 插入
            await self._insert(UserResourceBinding, binding)
        except Exception as e:
            logger.error(f"Failed to bind resource {resource_id} to user {user_id}: {e}")

    async def unbind(self, user_id: str, resource_id: str):
        """
        [Unlink] 解除绑定
        """
        try:
            # 直接使用 _delete_by，Backend Agnostic
            await self._delete_by(
                UserResourceBinding, 
                filters={
                    "user_id": user_id, 
                    "resource_id": resource_id
                }
            )
        except Exception as e:
            logger.error(f"Failed to unbind resource {resource_id} from user {user_id}: {e}")

    async def get_resource_ids(self, user_id: str, resource_type: ResourceType, limit: int = 100, offset: int = 0) -> List[str]:
        """
        [Query] 获取用户拥有的资源 ID 列表
        """
        try:
            # 1. 查找绑定记录
            bindings:List[UserResourceBinding] = await self._find(
                UserResourceBinding,
                filters={
                    "user_id": user_id,
                    "resource_type": resource_type
                },
                limit=limit,
                offset=offset
            )
            
            # 2. 内存排序 (按时间倒序)
            bindings.sort(key=lambda x: x.created_at, reverse=True)
            
            # 3. 提取 ID
            return [b.resource_id for b in bindings]
        except Exception as e:
            logger.error(f"Failed to get resource IDs for user {user_id}: {e}")

    async def check_ownership(self, user_id: str, resource_id: str) -> bool:
        """
        [Auth] 检查是否有权访问
        """
        try:
            # 使用 limit=1 进行高效查询
            results:List[UserResourceBinding] = await self._find(
                UserResourceBinding,
                filters={
                    "user_id": user_id,
                    "resource_id": resource_id
                },
                limit=1
            )
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to check ownership for user {user_id} and resource {resource_id}: {e}")
