import os
from pathlib import Path
from typing import Any, Dict, Set, List
from jinja2 import Environment, FileSystemLoader, select_autoescape, meta

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"

class PromptEngine:
    def __init__(self, template_dir: Path = DEFAULT_TEMPLATE_DIR):
        self.template_dir = template_dir
        # 关闭自动转义以支持 Markdown/YAML
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )

    def get_template_variables(self, template_name: str) -> Set[str]:
        """[新增] 自省：获取模板中定义的所有变量名"""
        template_source = self.env.loader.get_source(self.env, template_name)[0]
        parsed_content = self.env.parse(template_source)
        return meta.find_undeclared_variables(parsed_content)

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """渲染模板并进行基础校验"""
        # 1. 校验变量 (可选)
        required_vars = self.get_template_variables(template_name)
        missing_vars = required_vars - set(context.keys())
        # 注意：Jinja2 允许变量为空，但对于 Prompt 来说，缺少变量通常是 bug
        # 这里我们打印警告而不是报错，因为有些变量可能有默认值
        if missing_vars:
            print(f"⚠️ Warning: Template '{template_name}' missing variables: {missing_vars}")

        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            available = list(self.template_dir.glob("*"))
            raise ValueError(f"Failed to render '{template_name}': {e}. Available: {[p.name for p in available]}")