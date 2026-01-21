"""
Prompt Manager

Manages prompt templates and system prompts.
Reference: goose-rs prompt_manager.rs

Features:
- Prompt template storage
- Variable substitution
- Prompt versioning
- Prompt categories
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("goose.prompt")


class PromptCategory(str, Enum):
    """Prompt categories."""
    SYSTEM = "system"
    TASK = "task"
    TOOL = "tool"
    CONTEXT = "context"
    CUSTOM = "custom"


@dataclass
class PromptTemplate:
    """Prompt template with variables."""
    name: str
    content: str
    category: PromptCategory = PromptCategory.CUSTOM
    description: Optional[str] = None
    version: int = 1
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, variables: Dict[str, Any]) -> str:
        """Render template with variables."""
        content = self.content
        for var in self.variables:
            pattern = r'\{\{\s*' + re.escape(var) + r'\s*\}\}'
            value = str(variables.get(var, f"{{{{ {var} }}}}"))
            content = re.sub(pattern, value, content)
        return content

    def validate(self) -> tuple[bool, List[str]]:
        """Validate template syntax."""
        errors = []
        for var in self.variables:
            pattern = r'\{\{\s*' + re.escape(var) + r'\s*\}\}'
            if not re.search(pattern, self.content):
                errors.append(f"Variable {var} not found in template")

        found_vars = set(re.findall(r'\{\{\s*(\w+)\s*\}\}', self.content))
        for var in found_vars - set(self.variables):
            errors.append(f"Unknown variable: {var}")

        return len(errors) == 0, errors


@dataclass
class PromptContext:
    """Context for prompt rendering."""
    agent_name: str = "Goose"
    task_description: str = ""
    available_tools: List[Dict[str, Any]] = field(default_factory=list)
    active_skills: List[str] = field(default_factory=list)
    current_time: str = ""
    user_info: Optional[Dict[str, Any]] = None
    custom_variables: Dict[str, Any] = field(default_factory=dict)

    def to_variables(self) -> Dict[str, Any]:
        """Convert context to variables dict."""
        vars_dict = {
            "agent_name": self.agent_name,
            "task": self.task_description,
            "current_time": self.current_time,
            "tools": "\n".join([
                f"- {t.get('name', 'unknown')}: {t.get('description', '')}"
                for t in self.available_tools
            ]),
            "skills": ", ".join(self.active_skills) if self.active_skills else "None",
        }
        vars_dict.update(self.custom_variables)
        return vars_dict


class PromptProvider(ABC):
    """Abstract prompt provider."""

    @abstractmethod
    async def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        """Get a prompt by name."""
        pass


class MemoryPromptProvider(PromptProvider):
    """In-memory prompt provider."""

    def __init__(self):
        self._prompts: Dict[str, PromptTemplate] = {}

    async def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        return self._prompts.get(name)

    def add_prompt(self, prompt: PromptTemplate) -> None:
        self._prompts[prompt.name] = prompt


class FilePromptProvider(PromptProvider):
    """File-based prompt provider."""

    def __init__(self, base_path: str):
        self.base_path = base_path

    async def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        import os
        filepath = os.path.join(self.base_path, f"{name}.txt")
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
            return PromptTemplate(name=name, content=content)
        return None


class PromptManager:
    """
    Manages prompt templates and rendering.

    Reference: goose-rs PromptManager
    """

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._providers: List[PromptProvider] = [MemoryPromptProvider()]
        self._default_context: PromptContext = PromptContext()

    def register_template(self, template: PromptTemplate) -> None:
        """Register a prompt template."""
        self._templates[template.name] = template
        logger.info(f"Registered prompt template: {template.name}")

    def add_provider(self, provider: PromptProvider) -> None:
        """Add a prompt provider."""
        self._providers.insert(0, provider)

    def set_default_context(self, context: PromptContext) -> None:
        """Set default context for rendering."""
        self._default_context = context

    async def get_template(self, name: str) -> Optional[PromptTemplate]:
        """Get a prompt template by name."""
        if name in self._templates:
            return self._templates[name]

        for provider in self._providers:
            template = await provider.get_prompt(name)
            if template:
                return template

        return None

    def render(
        self,
        name: str,
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[PromptContext] = None
    ) -> str:
        """
        Render a prompt template.

        Args:
            name: Template name
            variables: Additional variables
            context: Prompt context

        Returns:
            Rendered prompt string
        """
        import asyncio
        template = asyncio.run(self.get_template(name))

        if not template:
            logger.warning(f"Prompt template not found: {name}")
            return f"[Template not found: {name}]"

        ctx = context or self._default_context
        vars_dict = ctx.to_variables()
        if variables:
            vars_dict.update(variables)

        return template.render(vars_dict)

    def render_system_prompt(
        self,
        task_description: str,
        tools: List[Dict[str, Any]],
        skills: Optional[List[str]] = None
    ) -> str:
        """Render system prompt for agent."""
        context = PromptContext(
            agent_name="Goose",
            task_description=task_description,
            available_tools=tools,
            active_skills=skills or [],
            current_time=self._get_timestamp()
        )

        return self.render("system", context=context)

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def list_templates(self) -> List[str]:
        """List all registered templates."""
        return list(self._templates.keys())

    def get_template_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get template metadata."""
        if name in self._templates:
            t = self._templates[name]
            return {
                "name": t.name,
                "category": t.category.value,
                "description": t.description,
                "version": t.version,
                "variables": t.variables
            }
        return None


def create_system_prompt(
    agent_name: str = "Goose",
    task_description: str = "",
    tools: Optional[List[Dict[str, Any]]] = None,
    skills: Optional[List[str]] = None
) -> str:
    """Create a default system prompt."""
    tools_str = ""
    if tools:
        tools_str = "\n".join([
            f"- **{t.get('name', 'unknown')}**: {t.get('description', '')}"
            for t in tools
        ])

    skills_str = ", ".join(skills) if skills else "None"

    return f"""You are {agent_name}, an AI assistant.

## Task
{task_description}

## Capabilities
You can use tools to perform actions. Each tool has a specific purpose.

## Available Tools
{tools_str if tools_str else "No tools available."}

## Skills
Active skills: {skills_str}

## Guidelines
1. Think step by step before taking action
2. Use tools only when necessary
3. Explain your reasoning
4. Ask for clarification when needed

Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
