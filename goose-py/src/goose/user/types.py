import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, EmailStr

class User(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    username: str
    email: Optional[str] = None  # 使用 EmailStr 需安装 pydantic[email]
    
    # [安全注意] Model 中通常包含 hashed_password 用于持久化，
    # 但在返回给前端的 API Response Model 中必须排除此字段！
    hashed_password: Optional[str] = None
    api_key: Optional[str] = None
    
    # 基础信息
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    
    # 状态
    is_active: bool = True
    is_superuser: bool = False
    
    roles: List[str] = Field(default_factory=list) # e.g. ["admin"]
    
    # 扩展字段 (Repository 自动转 JSON)
    profile: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)
    
    # 时间
    last_login_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    
    @property
    def display_name(self) -> str:
        """优先显示昵称，没有则显示用户名"""
        return self.nickname or self.username

class UserSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str
    
    # 存储 Refresh Token 的哈希，而不是明文
    refresh_token_hash: str
    
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    
    is_valid: bool = True
    expires_at: float # 必须指定过期时间
    
    created_at: float = Field(default_factory=time.time)
    last_used_at: float = Field(default_factory=time.time)
    
class ResourceType(str, Enum):
    WORKFLOW = "workflow"
    EXECUTION = "execution"
    FILE = "file"

class UserResourceBinding(BaseModel):
    """
    实体：用户与资源的关联关系
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str
    resource_id: str
    resource_type: ResourceType
    
    # 统一使用 float 时间戳
    created_at: float = Field(default_factory=time.time)