import os
from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, RootModel, Field, field_validator


class ToolConfig(BaseModel):
    """工具级别配置，用于覆盖工具的显示名称等属性。"""
    label: Optional[str] = None  # 工具中文显示名称
    description: Optional[str] = None  # 工具描述覆盖
    sensitive: Optional[bool] = None  # 是否敏感（覆盖代码定义）


class SkillConfig(BaseModel):
    """Per-skill configuration."""
    enabled: bool = True
    # [新增] 允许覆盖运行模式：'global', 'contextual'，不填则使用 SKILL.md 的定义
    mode: Optional[Literal['global', 'contextual']] = None
    description: Optional[str] = None
    # [新增] 技能中文显示名称，可配置覆盖
    label: Optional[str] = None
    sensitive_tools: List[str] = Field(default_factory=list)
    # [新增] 工具级别配置映射：tool_name -> ToolConfig
    tools_config: Dict[str, ToolConfig] = Field(default_factory=dict)


class SkillsConfig(RootModel[Dict[str, SkillConfig]]):
    """
    Skills configuration mapping.

    Structure:
      skill_name:
        enabled: true/false
        mode: "global" | "contextual"
        label: "中文显示名称"
        sensitive_tools: [tool1, tool2]
        tools_config:
          tool_name:
            label: "工具中文显示名称"
            description: "工具描述覆盖"
            sensitive: true/false
    """
    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)

    def get_enabled_skills(self) -> List[str]:
        """Get list of enabled skill names."""
        return [name for name, config in self.root.items() if config.enabled]

    def get_disabled_skills(self) -> List[str]:
        """Get list of disabled skill names."""
        return [name for name, config in self.root.items() if not config.enabled]