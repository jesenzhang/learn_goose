from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from goose.providers import ModelConfig
from .extension_data import ExtensionData

# --- 数据模型 ---

class SessionType(str, Enum):
    """对应 Rust: pub enum SessionType"""
    USER = "user"
    SCHEDULED = "scheduled"
    SUB_AGENT = "sub_agent"
    HIDDEN = "hidden"
    TERMINAL = "terminal"
    WORKFLOW = "workflow"

class Session(BaseModel):
    """
    对应 Rust: pub struct Session
    """
    id: str
    working_dir: str
    name: str = ""
    user_set_name: bool = False
    session_type: SessionType = SessionType.USER
    created_at: str
    updated_at: str
    # 1. 通用元数据：存放 working_dir, user_id 等
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # 扩展数据 (ExtensionData)
    extension_data: ExtensionData = Field(default_factory=ExtensionData)
    
    # Token 统计
    total_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    accumulated_total_tokens: Optional[int] = None
    accumulated_input_tokens: Optional[int] = None
    accumulated_output_tokens: Optional[int] = None
    
    # 上下文相关
    schedule_id: Optional[str] = None
    recipe_json: Optional[str] = None
    user_recipe_values: Optional[Dict[str, str]] = None
    
    # 运行时状态
    message_count: int = 0
    provider_name: Optional[str] = None
    
    # Pydantic v2 兼容性重命名
    current_model_config: Optional[ModelConfig] = Field(default=None, alias="model_config")
