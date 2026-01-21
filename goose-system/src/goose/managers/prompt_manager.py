"""
Prompt Manager

提示模板管理。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import re


class PromptCategory(str, Enum):
    """提示类别"""
    SYSTEM = "system"
    TASK = "task"
    CONTEXT = "context"
    TOOL = "tool"
    CUSTOM = "custom"


@dataclass
class PromptTemplate:
    """提示模板"""
    name: str
    content: str
    category: PromptCategory = PromptCategory.CUSTOM
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def render(self, context: Dict[str, Any]) -> str:
        """渲染模板"""
        result = self.content
        for var in self.variables:
            placeholder = "{" + var + "}"
            value = context.get(var, "{" + var + "}")
            result = result.replace(placeholder, str(value))
        return result


@dataclass
class PromptContext:
    """提示上下文"""
    base_prompt: str = ""
    task_description: str = ""
    available_tools: List[str] = field(default_factory=list)
    conversation_history: str = ""
    system_info: Dict[str, Any] = field(default_factory=dict)
    custom_context: Dict[str, Any] = field(default_factory=dict)


class PromptManager:
    """
    提示管理器
    
    职责：
    - 提示模板管理
    - 动态提示构建
    - 上下文注入
    """
    
    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self.template_order: List[str] = []
        self.context_injectors: List[Callable] = []
    
    def add_template(self, template: PromptTemplate) -> None:
        """添加模板"""
        self.templates[template.name] = template
        if template.name not in self.template_order:
            self.template_order.append(template.name)
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """获取模板"""
        return self.templates.get(name)
    
    def remove_template(self, name: str) -> bool:
        """移除模板"""
        if name in self.templates:
            del self.templates[name]
            self.template_order.remove(name)
            return True
        return False
    
    def list_templates(self, category: Optional[PromptCategory] = None) -> List[str]:
        """列出模板"""
        if category is None:
            return list(self.templates.keys())
        return [
            name for name, tmpl in self.templates.items()
            if tmpl.category == category
        ]
    
    def add_context_injector(
        self,
        injector: Callable[[PromptContext], Dict[str, Any]]
    ) -> None:
        """添加上下文注入器"""
        self.context_injectors.append(injector)
    
    def build_prompt(
        self,
        context: PromptContext,
        template_names: Optional[List[str]] = None
    ) -> str:
        """
        构建完整提示
        
        Args:
            context: 基础上下文
            template_names: 要使用的模板列表 (顺序重要)
            
        Returns:
            完整的提示文本
        """
        parts = []
        
        # 添加基础提示
        if context.base_prompt:
            parts.append(context.base_prompt)
        
        # 添加任务描述
        if context.task_description:
            parts.append(f"## Task\n{context.task_description}")
        
        # 添加模板
        names = template_names or self.template_order
        for name in names:
            template = self.templates.get(name)
            if template:
                rendered = template.render(self._context_to_dict(context))
                parts.append(f"## {template.category.value.upper()}\n{rendered}")
        
        # 添加上下文注入
        for injector in self.context_injectors:
            extra = injector(context)
            if extra:
                parts.append(f"## Extra Context\n{extra}")
        
        # 添加可用工具
        if context.available_tools:
            tools_str = ", ".join(context.available_tools)
            parts.append(f"## Available Tools\n{tools_str}")
        
        # 添加对话历史
        if context.conversation_history:
            parts.append(f"## Conversation History\n{context.conversation_history}")
        
        return "\n\n".join(parts)
    
    def _context_to_dict(self, context: PromptContext) -> Dict[str, Any]:
        """将上下文转换为字典"""
        return {
            "task": context.task_description,
            "tools": ", ".join(context.available_tools),
            "history": context.conversation_history,
            **context.system_info,
            **context.custom_context,
        }
    
    def create_system_prompt(
        self,
        task: str,
        tools: List[str],
        history: str = ""
    ) -> str:
        """快速创建系统提示"""
        context = PromptContext(
            task_description=task,
            available_tools=tools,
            conversation_history=history
        )
        return self.build_prompt(context)
