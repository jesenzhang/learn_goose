"""
Skill Registry

Skill 注册表，管理所有加载的 Skills。
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .base import Skill, SkillMetadata


@dataclass
class SkillInfo:
    """Skill 信息（用于注册表）"""
    name: str
    description: str
    path: str
    skill: Optional[Skill] = None
    enabled: bool = True
    priority: int = 0  # 优先级，数字越大优先级越高


class SkillRegistry:
    """
    Skill 注册表
    
    管理所有已加载的 Skills，支持：
    - 注册/注销
    - 启用/禁用
    - 优先级排序
    - 渐进式披露
    """
    
    def __init__(self):
        self._skills: Dict[str, SkillInfo] = {}
        self._enabled_count: int = 0
    
    @property
    def count(self) -> int:
        """获取注册表中的 Skill 数量"""
        return len(self._skills)
    
    @property
    def enabled_count(self) -> int:
        """获取启用的 Skill 数量"""
        return self._enabled_count
    
    def register(self, skill: Skill, enabled: bool = True, priority: int = 0) -> None:
        """
        注册 Skill
        
        Args:
            skill: Skill 实例
            enabled: 是否启用
            priority: 优先级
        """
        # 验证名称
        is_valid, error = skill.validate_name()
        if not is_valid:
            raise ValueError(f"Invalid skill name: {error}")
        
        name = skill.name
        
        # 如果已存在，更新或跳过
        if name in self._skills:
            existing = self._skills[name]
            if existing.enabled:
                # 已存在且启用，检查是否覆盖
                if priority >= existing.priority:
                    self._skills[name] = SkillInfo(
                        name=name,
                        description=skill.description,
                        path=skill.path,
                        skill=skill,
                        enabled=enabled,
                        priority=priority
                    )
            else:
                # 未启用，直接更新
                self._enabled_count += 1 if enabled else 0
                self._skills[name] = SkillInfo(
                    name=name,
                    description=skill.description,
                    path=skill.path,
                    skill=skill,
                    enabled=enabled,
                    priority=priority
                )
        else:
            self._enabled_count += 1 if enabled else 0
            self._skills[name] = SkillInfo(
                name=name,
                description=skill.description,
                path=skill.path,
                skill=skill,
                enabled=enabled,
                priority=priority
            )
    
    def unregister(self, name: str) -> Optional[Skill]:
        """
        注销 Skill
        
        Args:
            name: Skill 名称
            
        Returns:
            被注销的 Skill，如果不存在返回 None
        """
        info = self._skills.pop(name, None)
        if info and info.enabled:
            self._enabled_count -= 1
        return info.skill if info else None
    
    def enable(self, name: str) -> bool:
        """
        启用 Skill
        
        Args:
            name: Skill 名称
            
        Returns:
            是否成功启用
        """
        if name in self._skills:
            if not self._skills[name].enabled:
                self._enabled_count += 1
            self._skills[name].enabled = True
            return True
        return False
    
    def disable(self, name: str) -> bool:
        """
        禁用 Skill
        
        Args:
            name: Skill 名称
            
        Returns:
            是否成功禁用
        """
        if name in self._skills:
            if self._skills[name].enabled:
                self._enabled_count -= 1
            self._skills[name].enabled = False
            return True
        return False
    
    def get(self, name: str) -> Optional[Skill]:
        """获取 Skill"""
        info = self._skills.get(name)
        return info.skill if info else None
    
    def is_enabled(self, name: str) -> bool:
        """检查 Skill 是否启用"""
        info = self._skills.get(name)
        return info.enabled if info else False
    
    def list_skills(self, enabled_only: bool = False) -> List[Skill]:
        """
        列出所有 Skills
        
        Args:
            enabled_only: 只返回启用的
            
        Returns:
            Skill 列表
        """
        skills = []
        for info in self._skills.values():
            if not enabled_only or info.enabled:
                if info.skill:
                    skills.append(info.skill)
        return skills
    
    def list_skill_names(self, enabled_only: bool = False) -> List[str]:
        """
        列出所有 Skill 名称
        
        Args:
            enabled_only: 只返回启用的
            
        Returns:
            名称列表
        """
        names = []
        for info in self._skills.values():
            if not enabled_only or info.enabled:
                names.append(info.name)
        return names
    
    def get_by_category(self, category: str) -> List[Skill]:
        """
        按类别获取 Skills
        
        Args:
            category: 类别名称
            
        Returns:
            该类别下的 Skills
        """
        skills = []
        for info in self._skills.values():
            if info.enabled and info.skill:
                meta = info.skill.metadata
                skill_category = meta.metadata.get("category", "general")
                if skill_category == category:
                    skills.append(info.skill)
        return skills
    
    def get_metadata_list(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        获取元数据列表（用于渐进式披露）
        
        Args:
            enabled_only: 只返回启用的
            
        Returns:
            元数据字典列表
        """
        metadata = []
        for info in self._skills.values():
            if not enabled_only or info.enabled:
                if info.skill:
                    metadata.append(info.skill.to_metadata_dict())
        return metadata
    
    def get_prompt_content(self, enabled_only: bool = False) -> str:
        """
        获取用于系统提示的内容
        
        Args:
            enabled_only: 只返回启用的
            
        Returns:
            格式化的 Skills 列表
        """
        skills = self.list_skills(enabled_only)
        if not skills:
            return "(No skills available)"
        
        lines = []
        for skill in skills:
            lines.append(f"- **{skill.name}**: {skill.description}")
            if skill.metadata.allowed_tools:
                lines.append(f"  -> Allowed tools: {', '.join(skill.metadata.allowed_tools)}")
            lines.append(f"  -> Read `{skill.path}` for full instructions")
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """清空注册表"""
        self._skills.clear()
        self._enabled_count = 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_skills": len(self._skills),
            "enabled_skills": self._enabled_count,
            "disabled_skills": len(self._skills) - self._enabled_count,
            "skill_names": self.list_skill_names(),
        }
