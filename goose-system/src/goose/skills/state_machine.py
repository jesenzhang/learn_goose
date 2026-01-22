"""
Progressive Disclosure State Machine

实现三级渐进式披露模式:
- L1 (Awareness): 仅元数据
- L2 (Activation): 完整指令
- L3 (Execution): 脚本执行

Reference: Agent Skills 架构设计手册
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List, Any
from pathlib import Path
import os


class SkillState(Enum):
    """技能状态枚举"""
    AWARENESS = "awareness"      # L1: 仅元数据
    ACTIVATION = "activation"    # L2: 完整指令
    EXECUTION = "execution"      # L3: 脚本执行


@dataclass
class ProgressiveDisclosureState:
    """渐进式披露状态"""
    state: SkillState = SkillState.AWARENESS
    active_skills: Set[str] = field(default_factory=set)
    execution_skills: Set[str] = field(default_factory=set)


class ProgressiveDisclosureStateMachine:
    """
    渐进式披露状态机
    
    控制技能从 L1 -> L2 -> L3 的状态转换，
    实现 Token 预算优化（参考文档：节省 98% 成本）。
    """
    
    def __init__(self):
        self._state = ProgressiveDisclosureState()
        self._skill_content: Dict[str, str] = {}
        self._skill_resources: Dict[str, Dict[str, bytes]] = {}
    
    @property
    def current_state(self) -> SkillState:
        return self._state.state
    
    @property
    def active_skills(self) -> Set[str]:
        return self._state.active_skills
    
    @property
    def execution_skills(self) -> Set[str]:
        return self._state.execution_skills
    
    def get_awareness_prompt(self, skills_metadata: List[Dict[str, Any]]) -> str:
        """
        L1: 生成感知态提示
        
        仅包含技能名称和描述，不加载完整指令。
        用于 Agent 初始化或会话开始时。
        
        Reference: 文档 4.1 "你拥有以下能力：Skill Name: Description..."
        """
        if not skills_metadata:
            return "(No skills available)"
        
        lines = ["You have the following skills available. Use them when relevant:\n"]
        for meta in skills_metadata:
            name = meta.get('name', 'unknown')
            desc = meta.get('description', '')
            lines.append(f"- {name}: {desc}")
        
        return "\n".join(lines)
    
    def activate_skill(self, skill_name: str, full_content: str) -> None:
        """
        L2: 激活技能
        
        当 LLM 输出表明要使用某技能时，调用此方法。
        将完整 SKILL.md 内容注入到上下文。
        
        Reference: 文档 4.2 "将完整 Markdown 内容动态注入上下文窗口"
        """
        self._state.state = SkillState.ACTIVATION
        self._state.active_skills.add(skill_name)
        self._skill_content[skill_name] = full_content
    
    def get_activation_content(self, skill_name: str) -> Optional[str]:
        """L2: 获取激活态的完整指令"""
        return self._skill_content.get(skill_name)
    
    def enter_execution(self, skill_name: str, resource_dir: Path) -> None:
        """
        L3: 进入执行态
        
        当 LLM 生成代码尝试调用 scripts/ 时，调用此方法。
        收集资源文件用于沙箱挂载。
        
        Reference: 文档 4.3 "将该 Skill 目录挂载到代码执行沙箱"
        """
        self._state.state = SkillState.EXECUTION
        self._state.execution_skills.add(skill_name)
        
        resources = {}
        if resource_dir.exists():
            for root, dirs, files in os.walk(resource_dir):
                for f in files:
                    fpath = Path(root) / f
                    try:
                        rel_path = str(fpath.relative_to(resource_dir))
                        resources[rel_path] = fpath.read_bytes()
                    except Exception:
                        pass
        
        self._skill_resources[skill_name] = resources
    
    def get_execution_resources(self, skill_name: str) -> Dict[str, bytes]:
        """L3: 获取执行态的资源"""
        return self._skill_resources.get(skill_name, {})
    
    def deactivate(self, skill_name: str) -> None:
        """停用技能，清理状态"""
        self._state.active_skills.discard(skill_name)
        self._state.execution_skills.discard(skill_name)
        self._skill_content.pop(skill_name, None)
        self._skill_resources.pop(skill_name, None)
    
    def reset(self) -> None:
        """重置所有状态"""
        self._state = ProgressiveDisclosureState()
        self._skill_content.clear()
        self._skill_resources.clear()
    
    def get_state_report(self) -> Dict[str, Any]:
        """获取状态报告"""
        return {
            "current_state": self._state.state.value,
            "active_skills": list(self._state.active_skills),
            "execution_skills": list(self._state.execution_skills),
            "cached_content_count": len(self._skill_content),
            "cached_resources_count": len(self._skill_resources),
        }
