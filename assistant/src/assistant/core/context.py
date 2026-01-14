# core/schema.py 或 core/context.py

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class RequestContext(BaseModel):
    """
    封装单次请求的运行时参数
    这些数据通常不需要持久化到数据库，或者只在当前 Turn 有效
    """
    token: Optional[str] = None
    server_type: str = 'show'
    file_path: Optional[str] = None
    page_content: Optional[Dict[str, Any]] = None
    
    # 控制标志
    deep_thinking: bool = False
    is_deep_research: bool = False