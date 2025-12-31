from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class ResourceKind(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    KNOWLEDGE_BASE = "knowledge_base"

class ResourceScope(str, Enum):
    SYSTEM = "system" # 全局共享
    USER = "user"     # 用户私有

class ResourceMetadata(BaseModel):
    """
    [Struct] 资源元数据
    数据库和配置文件最终都映射为这个结构。
    """
    id: str
    kind: ResourceKind
    scope: ResourceScope
    
    # 核心映射字段
    provider: str            # e.g., "openai", "google_search"
    config: Dict[str, Any]   # e.g., {"model": "gpt-4", "api_key": "..."}