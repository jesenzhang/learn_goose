# src/goose/app/user/service.py

import uuid
import secrets
import logging
from typing import Dict, Any, Optional, List

from goose.user.types import User, ResourceType
from goose.user.repository import UserRepository, UserResourceRepository
from passlib.context import CryptContext

# 初始化密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

logger = logging.getLogger(__name__)

class UserService:
    def __init__(
        self, 
        repo: UserRepository = None, 
        resource_repo: UserResourceRepository = None
    ):
        # 依赖注入 (DI)
        self.repo = repo or UserRepository()
        self.resource_repo = resource_repo or UserResourceRepository()

    # =========================================================================
    # 1. 基础身份与鉴权 (Identity & Auth)
    # =========================================================================

    async def get_or_create_default_user(self) -> User:
        """
        [Bootstrap] 获取默认 Admin 用户，不存在则创建
        """
        # 尝试查找 ID 为 "admin" 的用户
        # 注意: 这里假设 Repository 的 get_by_id 是基于 BaseRepository._find 封装的
        admin = await self.repo.get_by_id("admin")
        
        if not admin:
            logger.info("👑 Initializing default admin user...")
            
            # 直接构造 Model，无需手动处理 JSON
            admin = await self.repo.create_user(
                id="admin",
                username="Administrator",
                hashed_password=pwd_context.hash("admin"),
                is_superuser=True,
                roles=["admin"],
                config={"theme": "dark"}
            )
            logger.info(f"✅ Default admin created. API Key: {default_key}")
        
        return admin
    
    # ==========================================
    # 场景一：基于密码的验证 (用于登录接口)
    # ==========================================
    async def authenticate_password(self, username: str, plain_password: str) -> Optional[User]:
        """
        [Login] 验证用户名和密码
        """
        # 1. 先根据用户名把用户捞出来
        user = await self.repo.get_by_username(username)
        if not user:
            return None
            
        # 2. 核心：比对哈希密码
        # pwd_context.verify(明文, 哈希值) 会自动处理盐值和算法
        if not user.hashed_password:
            return None
            
        if not pwd_context.verify(plain_password, user.hashed_password):
            return None
            
        # 3. 检查用户是否被封禁
        if not user.is_active:
            return None
            
        return user
    
     
    # =========================================================================
    # 2. 用户生命周期 (Lifecycle)
    # =========================================================================

    async def register_user(self, username: str, password: str, config: Dict[str, Any] = None) -> User:
        """
        [Lifecycle] 注册新用户
        """
        # 1. 检查重名 (Repository 应该有 get_by_username)
        existing = await self.repo.get_by_username(username)
        if existing:
            raise ValueError(f"Username '{username}' already exists")

        # 3. 持久化
        new_user = await self.repo.create_user(username=username,
            password=password,
            config=config or {})
        
        return new_user

    async def get_user(self, user_id: str) -> Optional[User]:
        """[Query] 获取用户详情"""
        return await self.repo.get_by_id(user_id)
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """[Query] 获取用户详情"""
        return await self.repo.get_by_username(username)
    
    # =========================================================================
    # 3. 配置管理 (Preferences)
    # =========================================================================

    async def update_user_config(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        [Config] 更新用户的全局配置 (Patch 更新)
        """
        # 1. 获取当前用户 (为了拿到旧配置)
        user:User = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        
        # 2. 内存合并字典 (Repository 已经把 JSON 转成了 Dict)
        current_config = user.config.copy()
        current_config.update(updates)
        
        # 3. 保存更新
        # Repository 会自动把 Dict 转回 JSON 字符串存库
        await self.repo.update_config(user_id, current_config)
        
        return current_config

    # =========================================================================
    # 4. 资源绑定 (Resource Binding)
    # =========================================================================

    async def grant_resource(self, user_id: str, resource_id: str, resource_type: ResourceType):
        """[ACL] 授予用户访问某资源的权限"""
        await self.resource_repo.bind(user_id, resource_id, resource_type)

    async def revoke_resource(self, user_id: str, resource_id: str):
        """[ACL] 撤销权限"""
        await self.resource_repo.unbind(user_id, resource_id)

    async def check_access(self, user_id: str, resource_id: str) -> bool:
        """[ACL] 检查权限"""
        # 1. 如果是 Admin，直接放行 (可选逻辑)
        user = await self.repo.get(user_id)
        if user and user.is_superuser:
            return True
            
        # 2. 检查 owner (需要在具体的 ResourceRepo 里查，或者这里只检查 user_resources 表)
        # 假设这里只检查 user_resources 表的共享关系
        return await self.resource_repo.check_ownership(user_id, resource_id)

    async def get_user_resources(self, user_id: str, resource_type: ResourceType) -> List[str]:
        """[Query] 获取用户拥有的所有 Workflow/Execution ID"""
        return await self.resource_repo.get_resource_ids(user_id, resource_type, limit=1000)