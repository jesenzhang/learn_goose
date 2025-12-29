# import re
# import logging
# from typing import Dict, Any, Optional

# # 避免循环引用：只引用类型，运行时不依赖
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .context import WorkflowContext

# logger = logging.getLogger("goose.workflow.resolver")

# # 匹配 {{ node_id.key }} 的正则
# REF_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*\}\}")

# class ValueResolver:
    
#     @staticmethod
#     def resolve(mapping: Dict[str, Any], context: "WorkflowContext", overrides: Dict[str, Any] = None) -> Dict[str, Any]:
#         """
#         入口方法：解析整个字典
#         """
#         resolved = {}
#         overrides = overrides or {}
        
#         for arg_name, template in mapping.items():
#             resolved[arg_name] = ValueResolver._resolve_any(template, context, overrides)
#         return resolved
    
#     @staticmethod
#     def _resolve_any(value: Any, context: "WorkflowContext", overrides: Dict[str, Any]) -> Any:
#         """递归解析任意类型"""
#         if isinstance(value, str):
#             return ValueResolver._resolve_string(value, context, overrides)
#         elif isinstance(value, dict):
#             return {k: ValueResolver._resolve_any(v, context, overrides) for k, v in value.items()}
#         elif isinstance(value, list):
#             return [ValueResolver._resolve_any(v, context, overrides) for v in value]
#         else:
#             return value

#     @staticmethod
#     def _resolve_string(template: str, context: "WorkflowContext", overrides: Dict[str, Any]) -> Any:
#         """解析单个字符串"""
#         if not template:
#             return template
        
#         template_str = template.strip() # 保留原始变量名用于下面引用

#         # 1. [优先] 检查是否是纯引用 (Exact Match)
#         # 如果整个字符串只是一个变量，且变量值不是字符串（如 dict/list），我们直接返回该对象，保持类型。
#         # 例如 input="{{ item }}"，而 item 是个字典。
        
#         # Check Override Exact Match
#         var_match = re.match(r"^\{\{\s*([a-zA-Z0-9_]+)\s*\}\}$", template_str)
#         if var_match:
#             key = var_match.group(1)
#             if key in overrides:
#                 return overrides[key]

#         # Check Node Reference Exact Match
#         ref_match = re.match(r"^\{\{\s*([a-zA-Z0-9_]+)\.(.+)\s*\}\}$", template_str)
#         if ref_match:
#             node_id = ref_match.group(1)
#             path_str = ref_match.group(2).strip()
#             val = ValueResolver._get_deep_value(context, node_id, path_str)
#             # 如果解析成功（非None），直接返回对象
#             if val is not None:
#                 return val

#         # 2. [Fallback] 字符串插值 (String Interpolation)
#         # 处理 "Hello {{ start.name }}!" 这种情况
#         # 使用 re.sub 替换所有出现的 {{ ... }}
        
#         def replace_callback(match):
#             # 获取 {{ key }} 内部的内容
#             content = match.group(1).strip()
            
#             # A. 尝试 Override
#             if content in overrides:
#                 return str(overrides[content])
            
#             # B. 尝试 Node Reference (node.path)
#             if "." in content:
#                 parts = content.split(".", 1)
#                 node_id = parts[0]
#                 path = parts[1]
#                 val = ValueResolver._get_deep_value(context, node_id, path)
#                 return str(val) if val is not None else match.group(0) # 找不到则保留原样
            
#             return match.group(0)

#         # 匹配 {{ anything }}
#         # 这里的正则去掉了 ^$，允许部分匹配
#         pattern = re.compile(r"\{\{\s*(.+?)\s*\}\}")
        
#         # 如果存在 {{}} 才进行替换，优化性能
#         if pattern.search(template):
#             return pattern.sub(replace_callback, template)

#         return template

#     @staticmethod
#     def _get_deep_value(context: "WorkflowContext", node_id: str, path_str: str) -> Any:
#         """从 Context 中提取深层数据"""
#         # 获取节点输出
#         node_output = context.node_outputs.get(node_id)
#         if node_output is None:
#             return None

#         current_data = node_output
#         keys = path_str.split(".")
        
#         try:
#             for k in keys:
#                 # 支持数组索引 list.0
#                 if isinstance(current_data, list) and k.isdigit():
#                     idx = int(k)
#                     if 0 <= idx < len(current_data):
#                         current_data = current_data[idx]
#                     else:
#                         return None
#                 # 支持字典 key
#                 elif isinstance(current_data, dict):
#                     current_data = current_data.get(k)
#                 # 支持对象属性 (Pydantic)
#                 elif hasattr(current_data, k):
#                     current_data = getattr(current_data, k)
#                 else:
#                     return None # 路径不存在
                
#                 if current_data is None:
#                     return None
#             return current_data
#         except Exception:
#             return None
        





import re
import logging
from typing import Dict, Any, Optional

from goose.utils.template import TemplateRenderer

# 避免循环引用
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .context import WorkflowContext

logger = logging.getLogger("goose.workflow.resolver")

class ValueResolver:
    """
    [Advanced] 智能变量解析器
    融合了 Regex 的对象引用能力和 Jinja2 的字符串渲染能力。
    """

    @staticmethod
    def resolve(mapping: Dict[str, Any], context: "WorkflowContext", overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        """入口：递归解析整个配置字典"""
        resolved = {}
        # 准备数据源：合并 Context Outputs 和 Overrides
        # Jinja2 需要一个扁平或层级的字典
        data_source = context.node_outputs.copy()
        if overrides:
            data_source.update(overrides)
            
        for arg_name, template in mapping.items():
            resolved[arg_name] = ValueResolver._resolve_any(template, data_source)
        return resolved

    @staticmethod
    def _resolve_any(value: Any, data_source: Dict[str, Any]) -> Any:
        """递归解析"""
        if isinstance(value, str):
            return ValueResolver._resolve_string_or_obj(value, data_source)
        elif isinstance(value, dict):
            return {k: ValueResolver._resolve_any(v, data_source) for k, v in value.items()}
        elif isinstance(value, list):
            return [ValueResolver._resolve_any(v, data_source) for v in value]
        else:
            return value

    @staticmethod
    def _resolve_string_or_obj(template: str, data_source: Dict[str, Any]) -> Any:
        """
        核心逻辑：区分“对象引用”和“字符串渲染”
        """
        if not template:
            return template
        
        template_stripped = template.strip()

        # 1. [对象引用] Exact Match -> 返回原始对象 (Dict/List/Object)
        # 场景：input_list="{{ some_node.data_list }}"，我们需要得到 List 而不是 String
        # Regex: 匹配 {{ variable }} 或 {{ variable.path.to.key }}
        # 注意：Jinja2 语法比较复杂，这里只匹配最简单的引用语法
        ref_match = re.match(r"^\{\{\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s*\}\}$", template_stripped)
        
        if ref_match:
            path = ref_match.group(1)
            val = ValueResolver._get_value_by_path(data_source, path)
            # 只有当确实找到了值（非 None），才直接返回对象
            # 如果没找到，可能它就是一个普通的字符串 "{{ nothing }}"，交给 Jinja 处理
            if val is not None:
                return val

        # 2. [字符串渲染] String Interpolation -> 返回 String
        # 场景："Hello {{ name }}!" -> "Hello Goose!"
        return TemplateRenderer.render(template, data_source)

    @staticmethod
    def _get_value_by_path(data: Any, path_str: str) -> Any:
        """
        手动实现的路径查找，用于第1步的对象引用。
        Jinja2 内部也有类似的逻辑，但为了拿到 Raw Object，我们需要手动走一遍。
        """
        keys = path_str.split(".")
        current = data
        try:
            for k in keys:
                if isinstance(current, dict):
                    current = current.get(k)
                elif isinstance(current, list) and k.isdigit():
                    current = current[int(k)]
                elif hasattr(current, k):
                    current = getattr(current, k)
                else:
                    return None
                
                if current is None:
                    return None
            return current
        except Exception:
            return None
        

# # 显式引用对象 (可选，方便代码里写，不用拼字符串)
class Selector:
    def __init__(self, node_id: str, key: str):
        self.node_id = node_id
        self.key = key
        
    def resolve_in_context(self, context: 'WorkflowContext'):
        return context.get_node_output(self.node_id, self.key)