"""
Skill Base

Skill 基类，参考 Agent Skills Specification 设计。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import re
import yaml


SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024


@dataclass
class SkillMetadata:
    """Skill 元数据"""
    name: str
    description: str
    path: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)
    
    def validate(self) -> tuple[bool, str]:
        """验证元数据"""
        if not self.name:
            return False, "name is required"
        if len(self.name) > MAX_SKILL_NAME_LENGTH:
            return False, "name exceeds 64 characters"
        if not SKILL_NAME_PATTERN.match(self.name):
            return False, "name must be lowercase alphanumeric with single hyphens"
        if not self.description:
            return False, "description is required"
        if len(self.description) > MAX_SKILL_DESCRIPTION_LENGTH:
            return False, "description exceeds 1024 characters"
        return True, ""


class Skill(ABC):
    """
    Skill 基类
    
    Skill 是 Agent 的可复用能力单元，包含：
    - 元数据（名称、描述、版本等）
    - 工具定义
    - 系统提示
    - 使用示例
    """
    
    def __init__(self, metadata: SkillMetadata, content: str):
        self.metadata = metadata
        self.content = content
        self._tools: List[Dict[str, Any]] = []
        self._system_prompt: str = ""
        self._examples: List[str] = []
        self._parse_content()
    
    def _parse_content(self) -> None:
        """解析 Skill 内容"""
        # 提取工具定义
        tool_pattern = r"```json\s*\n(.*?)\n```"
        for match in re.finditer(tool_pattern, self.content, re.DOTALL):
            try:
                tool = yaml.safe_load(match.group(1))
                if tool and "name" in tool:
                    self._tools.append(tool)
            except yaml.YAMLError:
                pass
        
        # 提取系统提示（# System Prompt 部分）
        system_pattern = r"#+\s*System\s*Prompt\s*\n(.*?)(?=\n#+|\Z)"
        for match in re.finditer(system_pattern, self.content, re.DOTALL | re.IGNORECASE):
            self._system_prompt = match.group(1).strip()
            break
        
        # 提取示例（# Example 部分）
        example_pattern = r"#+\s*Example\s*\n(.*?)(?=\n#+|\Z)"
        for match in re.finditer(example_pattern, self.content, re.DOTALL | re.IGNORECASE):
            self._examples.append(match.group(1).strip())
    
    @property
    def name(self) -> str:
        """Skill 名称"""
        return self.metadata.name
    
    @property
    def description(self) -> str:
        """Skill 描述"""
        return self.metadata.description
    
    @property
    def path(self) -> str:
        """Skill 文件路径"""
        return self.metadata.path
    
    @property
    def tools(self) -> List[Dict[str, Any]]:
        """获取工具定义"""
        return self._tools
    
    @property
    def system_prompt(self) -> str:
        """获取系统提示"""
        return self._system_prompt
    
    @property
    def examples(self) -> List[str]:
        """获取使用示例"""
        return self._examples
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """获取工具定义（兼容性方法）"""
        return self._tools
    
    def get_prompt_for_model(self) -> str:
        """获取用于模型的提示（渐进式披露）"""
        return f"""
## Skill: {self.metadata.name}

**Description**: {self.metadata.description}

**Location**: `{self.metadata.path}`

**Allowed Tools**: {', '.join(self.metadata.allowed_tools) if self.metadata.allowed_tools else 'None'}

**Usage**:
Read `{self.metadata.path}` for full instructions.

**Examples**:
{chr(10).join(f"- {ex}" for ex in self._examples[:3])}
"""
    
    def to_metadata_dict(self) -> Dict[str, Any]:
        """转换为元数据字典"""
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "path": self.metadata.path,
            "license": self.metadata.license,
            "compatibility": self.metadata.compatibility,
            "metadata": self.metadata.metadata,
            "allowed_tools": self.metadata.allowed_tools,
        }
    
    def validate_name(self) -> tuple[bool, str]:
        """验证 Skill 名称"""
        return self.metadata.validate()
    
    def __repr__(self) -> str:
        return f"Skill(name='{self.name}', description='{self.description[:50]}...')"


def parse_skill_metadata(content: str, skill_path: str) -> Optional[SkillMetadata]:
    """解析 Skill 文件的 YAML 前言"""
    # 提取 YAML 前言
    frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if not match:
        return None
    
    try:
        data = yaml.safe_load(match.group(1))
        if not isinstance(data, dict):
            return None
        
        name = data.get("name", "")
        description = data.get("description", "")
        
        if not name or not description:
            return None
        
        allowed_tools_raw = data.get("allowed-tools")
        if isinstance(allowed_tools_raw, list):
            allowed_tools = [str(t).strip() for t in allowed_tools_raw]
        elif isinstance(allowed_tools_raw, str):
            allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]
        else:
            allowed_tools = []
        
        return SkillMetadata(
            name=name,
            description=description[:MAX_SKILL_DESCRIPTION_LENGTH],
            path=skill_path,
            license=data.get("license"),
            compatibility=data.get("compatibility"),
            metadata=data.get("metadata", {}),
            allowed_tools=allowed_tools
        )
    except yaml.YAMLError:
        return None
