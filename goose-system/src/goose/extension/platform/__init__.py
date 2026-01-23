"""
Platform Extensions

平台扩展模块，提供内置的平台功能：
- Skills: 技能管理
- Developer: 开发工具 (文本编辑、shell、分析)
- ComputerController: 计算机控制 (网页抓取、文档处理、自动化)
- Memory: 记忆存储
- Tutorial: 教程加载
- AutoVisualiser: 自动可视化
"""

from .skills import (
    SkillsMcpServer,
    SkillsPlatformExtension,
    create_skills_extension,
)

from .developer import (
    DeveloperPlatformExtension,
    create_developer_extension,
)

from .computercontroller import (
    ComputerControllerPlatformExtension,
    create_computer_controller_extension,
)

from .memory import (
    MemoryPlatformExtension,
    create_memory_extension,
)

from .tutorial import (
    TutorialPlatformExtension,
    create_tutorial_extension,
)

from .autovisualiser import (
    AutoVisualiserPlatformExtension,
    create_auto_visualiser_extension,
)

__all__ = [
    # Skills
    "SkillsMcpServer",
    "SkillsPlatformExtension",
    "create_skills_extension",
    # Developer
    "DeveloperPlatformExtension",
    "create_developer_extension",
    # ComputerController
    "ComputerControllerPlatformExtension",
    "create_computer_controller_extension",
    # Memory
    "MemoryPlatformExtension",
    "create_memory_extension",
    # Tutorial
    "TutorialPlatformExtension",
    "create_tutorial_extension",
    # AutoVisualiser
    "AutoVisualiserPlatformExtension",
    "create_auto_visualiser_extension",
]
