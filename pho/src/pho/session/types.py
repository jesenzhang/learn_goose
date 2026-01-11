from enum import Enum
import time
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from .extension_data import ExtensionData
from ..providers import ModelConfig

# --- 数据模型 ---

class SessionType(str, Enum):
    """对应 Rust: pub enum SessionType"""
    USER = "user"
    SCHEDULED = "scheduled"
    SUB_AGENT = "sub_agent"
    HIDDEN = "hidden"
    TERMINAL = "terminal"
    WORKFLOW = "workflow"

class TokenStats(BaseModel):
    total_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    accumulated_total_tokens: Optional[int] = None
    accumulated_input_tokens: Optional[int] = None
    accumulated_output_tokens: Optional[int] = None
    
class Session(BaseModel):
    """
    对应 Rust: pub struct Session
    """
    id: str
    working_dir: str = Field(default=".", description="（工作目录）是一个至关重要的概念，尤其是在涉及 代码执行（Code Interpreter）、文件处理 和 持久化会话 时,简单来说，它是该 Session 独占的文件系统沙箱（Sandbox）")
    name: str = Field(default="", description="（会话名称）用户设置的名称，用于识别和组织会话")
    user_set_name: bool = Field(default=False, description="（用户设置名称）指示会话名称是否由用户设置")
    session_type: SessionType = Field(default=SessionType.USER, description="（会话类型）会话的类型，表示会话的用途和行为")
    created_at: float = Field(default_factory=time.time, description="（创建时间）会话的创建时间戳")
    updated_at: float = Field(default_factory=time.time, description="（更新时间）会话的最后更新时间戳")
    # 1. 通用元数据：存放 working_dir, user_id 等
    metadata: Dict[str, Any] = Field(default_factory=dict, description="（元数据）存放 working_dir, user_id 等通用元数据")
    # 扩展数据 (ExtensionData)
    extension_data: ExtensionData = Field(default_factory=ExtensionData, description="（扩展数据）存放扩展数据，如工具、插件等")
    
    # Token 统计
    stats: TokenStats = Field(default_factory=TokenStats, description="（Token 统计）存放 Token 统计信息")
    
    # 上下文相关
    schedule_id: Optional[str] = Field(default=None, description="（计划 ID）关联的计划 ID")
    recipe_json: Optional[str] = Field(default=None, description="（食谱 JSON）关联的食谱 JSON")
    user_recipe_values: Optional[Dict[str, str]] = Field(default=None, description="（用户食谱值）用户设置的食谱值")
    
    # 运行时状态
    message_count: int = Field(default=0, description="（消息计数）会话中消息的数量")
    provider_name: Optional[str] = Field(default=None, description="（提供者名称）关联的提供者名称")
    
    # Pydantic v2 兼容性重命名
    current_model_config: Optional[ModelConfig] = Field(default=None, alias="model_config")
