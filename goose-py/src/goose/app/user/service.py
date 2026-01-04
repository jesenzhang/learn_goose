import uuid
import secrets
import logging
from typing import Optional, Dict, Any
from .repository import UserRepository,UserResourceRepository

logger = logging.getLogger("goose.app.user")

class UserService:
    def __init__(self, repo: UserRepository, resource_repo: UserResourceRepository):
        self.repo:UserRepository = repo
        self.resource_repo:UserResourceRepository = resource_repo

    # --- 1. 基础流程 (Dev Mode) ---
    
    async def get_or_create_default_user(self) -> str:
        """[Existing] 获取默认 Admin"""
        admin = await self.repo.get_by_id("admin")
        if not admin:
            # 创建时生成一个默认 API Key
            default_key = f"sk-goose-{secrets.token_hex(16)}"
            await self.repo.create(
                user_id="admin", 
                username="Administrator", 
                api_key=default_key
            )
            logger.info(f"👑 Created default admin. API Key: {default_key}")
        return "admin"

    # --- 2. 鉴权与安全 (Authentication) ---

    async def authenticate_by_api_key(self, api_key: str) -> Optional[str]:
        """
        [Auth] 根据 API Key 验证身份
        用于 deps.py 中的 get_current_user_id
        :return: user_id or None
        """
        if not api_key:
            return None
            
        user = await self.repo.get_by_api_key(api_key)
        if user:
            return user["id"]
        return None

    async def regenerate_api_key(self, user_id: str) -> str:
        """
        [Security] 重置用户的 API Key
        """
        new_key = f"sk-goose-{secrets.token_hex(16)}"
        await self.repo.update_field(user_id, "api_key", new_key)
        logger.info(f"🔐 Rotated API Key for user {user_id}")
        return new_key

    # --- 3. 用户管理 (Management) ---

    async def register_user(self, username: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        [Lifecycle] 注册新用户
        """
        user_id = f"u_{uuid.uuid4().hex[:12]}"
        api_key = f"sk-goose-{secrets.token_hex(16)}"
        
        await self.repo.create(
            user_id=user_id, 
            username=username, 
            api_key=api_key,
            config=config or {}
        )
        
        return {
            "id": user_id,
            "username": username,
            "api_key": api_key # 仅在创建时返回一次
        }

    async def get_user_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        [Query] 获取用户信息 (脱敏)
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            return None
        
        # 转换为 Dict 并移除敏感信息（如果不想返回完整 Key）
        data = dict(user)
        # data["api_key"] = "***" # 可选掩码处理
        return data

    # --- 4. 配置管理 (Preferences) ---

    async def update_user_config(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        [Config] 更新用户的全局配置 JSON
        例如：{"default_llm": "gpt-4", "theme": "dark"}
        """
        # 1. 获取现有配置
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        
        import json
        current_config = json.loads(user["config"]) if user["config"] else {}
        
        # 2. 合并配置
        current_config.update(updates)
        
        # 3. 保存
        await self.repo.update_field(user_id, "config", json.dumps(current_config))
        return current_config