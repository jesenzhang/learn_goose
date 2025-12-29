import logging
from typing import Dict, Any, Optional
from jinja2 import Environment, BaseLoader, Undefined

logger = logging.getLogger("goose.utils.prompt_engine")

# 1. 自定义未定义变量的行为：不报错，返回空字符串
# 这与 TemplateRenderer 的默认行为一致，适合 UI 渲染场景
class SilentUndefined(Undefined):
    def _fail_with_undefined_error(self, *args, **kwargs):
        return ""
    
    def __str__(self):
        return ""

class TemplateRenderer:
    """
    统一的 Jinja2 渲染引擎。
    替代 TemplateRenderer，用于处理 Prompt 生成和组件配置渲染。
    """
    
    # 初始化全局环境
    # autoescape=False: 因为我们主要处理 Text/Markdown/JSON，不是 HTML
    _env = Environment(
        loader=BaseLoader(), 
        autoescape=False, 
        undefined=SilentUndefined
    )

    @staticmethod
    def render(template_str: str, context: Dict[str, Any]) -> str:
        """
        渲染模版字符串。
        
        Args:
            template_str: 包含 {{ var }} 的字符串
            context: 变量字典
        """
        if not template_str:
            return ""
        
        # 如果不是字符串，直接转换为字符串返回 (容错)
        if not isinstance(template_str, str):
            return str(template_str)

        # 性能优化：如果不包含 {{，直接返回原字符串，跳过 Jinja 编译
        if "{{" not in template_str:
            return template_str

        try:
            # from_string 会利用 Environment 的缓存机制
            template = TemplateRenderer._env.from_string(template_str)
            return template.render(**context)
        except Exception as e:
            logger.warning(f"PromptEngine render failed: {e}. Raw: '{template_str[:50]}...'")
            # 降级策略：返回原始字符串
            return template_str

    @staticmethod
    def validate(template_str: str) -> bool:
        """校验模版语法是否正确"""
        try:
            TemplateRenderer._env.parse(template_str)
            return True
        except Exception:
            return False      
        
        
         
# class TemplateRenderer:
#     """
#     基于 Jinja2 的轻量级字符串渲染工具。
#     用于组件内部将 inputs 数据填充到 config 字符串中。
#     """
    
#     @staticmethod
#     def render(template_str: str, variables: Dict[str, Any]) -> str:
#         """
#         渲染模板。
        
#         Args:
#             template_str: 包含 {{ variable }} 的字符串
#             variables: 用于替换的数据字典
            
#         Returns:
#             渲染后的字符串。如果出错，返回原字符串并记录警告。
#         """
#         if not template_str:
#             return ""
            
#         if not isinstance(template_str, str):
#             return str(template_str)

#         try:
#             # 使用 Jinja2 Template
#             # 默认配置下，未定义的变量会被渲染为空字符串，不会报错
#             t = Template(template_str)
#             return t.render(**variables)
#         except Exception as e:
#             logger.warning(f"Template rendering failed: {e}. Template: '{template_str[:50]}...'")
#             # 降级策略：返回原始字符串，防止流程崩溃
#             return template_str