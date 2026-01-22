"""
Platform Extensions

平台扩展模块，提供内置的平台功能：
- Skills: 技能管理
- Todo: 待办事项
- ChatRecall: 聊天记录回忆
- CodeExecution: 代码执行
"""

from .skills import (
    SkillsMcpServer,
    SkillsPlatformExtension,
    create_skills_extension,
)

__all__ = [
    "SkillsMcpServer",
    "SkillsPlatformExtension",
    "create_skills_extension",
]
