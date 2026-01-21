"""
Skill Implementation Loader

从 impl.py 文件加载技能实现，创建 FunctionTool 实例。
支持与 SKILL.md 中的 allowed-tools 配置映射。
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Any as TypeAny
import importlib.util
import inspect
import sys


def load_impl_module(impl_path: str) -> Optional[Any]:
    """
    动态加载 impl.py 模块
    
    Args:
        impl_path: impl.py 文件路径
        
    Returns:
        加载的模块，如果失败返回 None
    """
    p = Path(impl_path)
    if not p.exists():
        return None
    
    try:
        spec = importlib.util.spec_from_file_location("skill_impl", impl_path)
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        sys.modules["skill_impl"] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def get_callable_from_module(module: Any, name: str) -> Optional[Callable[..., Any]]:
    """
    从模块中获取指定名称的可调用对象
    
    Args:
        module: 加载的模块
        name: 函数名
        
    Returns:
        可调用对象，如果不存在返回 None
    """
    if not hasattr(module, name):
        return None
    
    obj = getattr(module, name)
    if not callable(obj):
        return None
    
    return obj


def create_tool_from_impl_function(
    func: Callable[..., Any],
    tool_name: Optional[str] = None
) -> "goose.tools.FunctionTool":
    """
    从 impl.py 函数创建 FunctionTool
    
    Args:
        func: Python 函数
        tool_name: 可选的工具名称（默认为函数名）
        
    Returns:
        FunctionTool 实例
    """
    from goose.tools.base import FunctionTool, inspect as tool_inspect
    
    name = tool_name or func.__name__
    doc = inspect.getdoc(func) or ""
    
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        if param_name == "_state":
            continue
        
        param_type = "string"
        if param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"
        elif param.annotation is bool:
            param_type = "boolean"
        
        properties[param_name] = {
            "type": param_type,
            "description": f"Parameter: {param_name}"
        }
        
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    
    parameters = {
        "type": "object",
        "properties": properties,
        "required": required
    }
    
    requires_state = "_state" in sig.parameters
    
    return FunctionTool(
        name=name,
        description=doc,
        function=func,
        parameters=parameters,
        requires_state=requires_state
    )


class SkillImplLoader:
    """
    Skill 实现加载器
    
    从 skill 目录加载 SKILL.md 和 impl.py，
    创建 Skill 实例和对应的 FunctionTool 映射。
    """
    
    def __init__(self, skills_path: str):
        """
        初始化加载器
        
        Args:
            skills_path: skills 根目录路径
        """
        self.skills_path = Path(skills_path)
    
    def load_impl_tools_from_skill(
        self,
        skill_dir: str
    ) -> Dict[str, "goose.tools.FunctionTool"]:
        """
        从 skill 目录加载所有工具实现
        
        Args:
            skill_dir: skill 目录路径
            
        Returns:
            工具名称到 FunctionTool 的映射
        """
        from goose.tools.base import FunctionTool
        
        tools: Dict[str, FunctionTool] = {}
        skill_path = Path(skill_dir)
        
        impl_path = skill_path / "impl.py"
        if not impl_path.exists():
            return tools
        
        module = load_impl_module(str(impl_path))
        if module is None:
            return tools
        
        skill_md_path = skill_path / "SKILL.md"
        allowed_tools = self._parse_allowed_tools(str(skill_md_path)) if skill_md_path.exists() else []
        
        for name in dir(module):
            if name.startswith("_"):
                continue
            
            obj = getattr(module, name)
            if not callable(obj):
                continue
            
            if allowed_tools and name not in allowed_tools:
                continue
            
            try:
                tool = create_tool_from_impl_function(obj)
                tools[name] = tool
            except Exception:
                continue
        
        return tools
    
    def _parse_allowed_tools(self, skill_md_path: str) -> List[str]:
        """解析 SKILL.md 中的 allowed-tools"""
        try:
            content = Path(skill_md_path).read_text(encoding="utf-8")
            
            import re
            import yaml
            
            frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
            match = re.match(frontmatter_pattern, content, re.DOTALL)
            
            if match:
                data = yaml.safe_load(match.group(1))
                if isinstance(data, dict):
                    allowed = data.get("allowed-tools", "")
                    if isinstance(allowed, str):
                        return [t.strip() for t in allowed.strip("[]").split(",") if t.strip()]
                    elif isinstance(allowed, list):
                        return allowed
        except Exception:
            pass
        
        return []
    
    def load_all_impl_tools(self) -> Dict[str, Dict[str, "goose.tools.FunctionTool"]]:
        """
        从 skills 目录加载所有 skill 的工具实现
        
        Returns:
            skill 名称到工具映射的字典
        """
        from goose.tools.base import FunctionTool
        
        all_tools: Dict[str, Dict[str, FunctionTool]] = {}
        
        if not self.skills_path.exists():
            return all_tools
        
        for item in self.skills_path.iterdir():
            if not item.is_dir():
                continue
            
            skill_name = item.name
            tools = self.load_impl_tools_from_skill(str(item))
            
            if tools:
                all_tools[skill_name] = tools
        
        return all_tools


def load_skill_with_implementation(skill_dir: str) -> Dict[str, Any]:
    """
    加载完整的 skill（包含元数据和工具实现）
    
    Args:
        skill_dir: skill 目录路径
        
    Returns:
        包含 metadata, skill, tools 的字典
    """
    from goose.skills.base import Skill, SkillMetadata, parse_skill_metadata
    from goose.tools.base import FunctionTool
    
    result: Dict[str, Any] = {
        "metadata": None,
        "skill": None,
        "tools": {}
    }
    
    skill_path = Path(skill_dir)
    
    skill_md_path = skill_path / "SKILL.md"
    if skill_md_path.exists():
        content = skill_md_path.read_text(encoding="utf-8")
        metadata = parse_skill_metadata(content, str(skill_md_path))
        result["metadata"] = metadata
        result["skill"] = Skill(metadata, content) if metadata else None
    
    impl_loader = SkillImplLoader(str(skill_path.parent))
    result["tools"] = impl_loader.load_impl_tools_from_skill(str(skill_path))
    
    return result
