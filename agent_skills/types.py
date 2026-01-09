import json
import logging
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
logger = logging.getLogger(__name__)



from skill_micro_agent.conversation.message import RawContent,CallToolResult

# =============================================================================
# 1. 修正后的 Type 定义
# =============================================================================

# class RawContent(BaseModel):
#     """
#     内容单元：承载 Artifact 的核心
#     """
#     type: Literal["text", "dataset", "image", "code", "error"] = "text"
#     text: Optional[str] = None
#     data: Optional[Any] = None
#     mime_type: Optional[str] = Field(None, alias="mimeType")

# class CallToolResult(BaseModel):
#     """工具函数的直接返回类型"""
#     content: List[RawContent] = Field(default_factory=list)
#     is_error: bool = Field(default=False, alias="isError")

#     @classmethod
#     def from_text(cls, text: str):
#         """返回纯文本结果"""
#         return cls(content=[RawContent(type="text", text=text)])

#     @classmethod
#     def from_artifact(cls, view: str, data: Any, type="dataset"):
#         """返回带数据的 Artifact 结果 (View + Data)"""
#         return cls(content=[
#             RawContent(type=type, text=view, data=data)
#         ])

#     @classmethod
#     def failure(cls, error_message: str):
#         """返回错误结果"""
#         return cls(
#             content=[RawContent(type="error", text=error_message)],
#             is_error=True
#         )

