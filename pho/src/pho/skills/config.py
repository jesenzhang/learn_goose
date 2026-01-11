import os
from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, RootModel, Field, field_validator

class SkillConfig(BaseModel):
    """Per-skill configuration."""
    enabled: bool = True
    # [新增] 允许覆盖运行模式：'global', 'contextual'，不填则使用 SKILL.md 的定义
    mode: Optional[Literal['global', 'contextual']] = None
    description: Optional[str] = None
    sensitive_tools: List[str] = Field(default_factory=list)

class SkillsConfig(RootModel[Dict[str, SkillConfig]]):
    """
    Skills configuration mapping.

    Structure:
      skill_name:
        enabled: true/false
        sensitive_tools: [tool1, tool2]
    """
    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)

    def get_enabled_skills(self) -> List[str]:
        """Get list of enabled skill names."""
        return [name for name, config in self.root.items() if config.enabled]

    def get_disabled_skills(self) -> List[str]:
        """Get list of disabled skill names."""
        return [name for name, config in self.root.items() if not config.enabled]