"""
Path Discovery - 标准路径发现器

功能:
- 发现 ~/.claude/skills/ (用户级)
- 发现 ./.claude/skills/ (项目级)
- 支持优先级覆盖 (项目级 > 用户级)
- 支持自定义路径

Reference: Agent Skills 架构设计手册 - 标准目录结构规范
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import os


class PathDiscoveryResult:
    """路径发现结果"""
    
    def __init__(
        self,
        paths: Dict[str, Path],
        priority_order: List[str]
    ):
        self.paths = paths  # {level: path}
        self.priority_order = priority_order  # [level1, level2, ...]
    
    def get_path(self, level: str) -> Optional[Path]:
        """获取指定级别的路径"""
        return self.paths.get(level)
    
    def get_all_paths(self) -> List[Path]:
        """获取所有路径 (按优先级排序)"""
        return [self.paths[l] for l in self.priority_order if l in self.paths]
    
    def get_merged_dir(self) -> Optional[Path]:
        """获取合并的技能目录 (如果有)"""
        merged = self.paths.get("merged")
        return merged if merged and merged.exists() else None
    
    def __repr__(self) -> str:
        return f"PathDiscoveryResult(paths={self.paths}, priority={self.priority_order})"


class StandardPathDiscovery:
    """
    标准路径发现器
    
    发现并管理技能的标准扫描路径。
    路径优先级 (低到高):
    1. user: ~/.claude/skills/ (用户级，全局可用)
    2. project: ./.claude/skills/ (项目级，仅当前上下文)
    
    注意: 后面的路径会覆盖前面同名的技能
    """
    
    # 默认路径级别定义 (优先级从低到高)
    DEFAULT_LEVELS = [
        ("user", "User Level", "~/.claude/skills"),
        ("project", "Project Level", "./.claude/skills"),
    ]
    
    # 额外的标准路径
    EXTRA_PATHS = [
        ("goose_user", "Goose User", "~/.goose/skills"),
        ("goose_project", "Goose Project", "./.goose/skills"),
        ("agents_user", "Agents User", "~/.config/agents/skills"),
    ]
    
    def __init__(self, include_extra: bool = False):
        """
        初始化路径发现器
        
        Args:
            include_extra: 是否包含额外路径
        """
        self._levels = list(self.DEFAULT_LEVELS)
        if include_extra:
            self._levels.extend(self.EXTRA_PATHS)
    
    @property
    def levels(self) -> List[Tuple[str, str, str]]:
        """获取所有路径级别定义"""
        return self._levels
    
    def discover(self) -> PathDiscoveryResult:
        """
        发现所有标准路径
        
        Returns:
            PathDiscoveryResult: 路径发现结果
        """
        paths: Dict[str, Path] = {}
        priority_order: List[str] = []
        
        for level, _, path_str in self._levels:
            # 处理路径中的 ~ 
            if path_str.startswith("~"):
                expanded = os.path.expanduser(path_str)
                path = Path(expanded)
            else:
                path = Path(path_str)
            
            # 检查路径是否存在
            if path.exists() and path.is_dir():
                paths[level] = path
                priority_order.append(level)
        
        return PathDiscoveryResult(paths, priority_order)
    
    def discover_with_override(
        self,
        custom_paths: Optional[List[str]] = None
    ) -> Tuple[Dict[str, Path], List[str]]:
        """
        发现路径并返回覆盖顺序
        
        用于 SkillLoader 的 discover_skills_in_directories
        
        Args:
            custom_paths: 自定义路径列表
            
        Returns:
            (路径字典, 优先级列表)
        """
        result = self.discover()
        
        paths = dict(result.paths)
        priority_order = list(result.priority_order)
        
        # 添加自定义路径
        if custom_paths:
            custom_level = "custom"
            for i, path_str in enumerate(custom_paths):
                path = Path(path_str)
                if path.exists() and path.is_dir():
                    paths[path_str] = path
                    priority_order.append(f"{custom_level}_{i}")
        
        return paths, priority_order
    
    def get_scan_directories(
        self,
        include_user: bool = True,
        include_project: bool = True,
        custom_paths: Optional[List[str]] = None
    ) -> List[Path]:
        """
        获取扫描目录列表 (按优先级排序)
        
        Args:
            include_user: 是否包含用户级目录
            include_project: 是否包含项目级目录
            custom_paths: 自定义路径
            
        Returns:
            路径列表 (后面的会覆盖前面的)
        """
        directories: List[Path] = []
        result = self.discover()
        
        # 按优先级添加
        for level in result.priority_order:
            if level == "user" and not include_user:
                continue
            if level == "project" and not include_project:
                continue
            
            path = result.paths[level]
            if path not in directories:
                directories.append(path)
        
        # 添加自定义路径
        if custom_paths:
            for path_str in custom_paths:
                path = Path(path_str)
                if path.exists() and path.is_dir():
                    if path not in directories:
                        directories.append(path)
        
        return directories
    
    def check_path_exists(self, path: str) -> bool:
        """检查路径是否存在"""
        p = Path(os.path.expanduser(path))
        return p.exists() and p.is_dir()
    
    def create_skill_directory(
        self,
        skill_name: str,
        level: str = "project"
    ) -> Tuple[Path, bool]:
        """
        创建技能目录
        
        Args:
            skill_name: 技能名称
            level: 路径级别 ("user" 或 "project")
            
        Returns:
            (路径, 是否成功)
        """
        result = self.discover()
        base_path = result.get_path(level)
        
        if not base_path:
            # 尝试创建基础目录
            if level == "user":
                base_path = Path.home() / ".claude" / "skills"
            else:
                base_path = Path.cwd() / ".claude" / "skills"
            
            try:
                base_path.mkdir(parents=True, exist_ok=True)
            except Exception:
                return Path(), False
        
        skill_dir = base_path / skill_name
        
        try:
            skill_dir.mkdir(exist_ok=True)
            return skill_dir, True
        except Exception:
            return Path(), False
    
    def get_priority_report(self) -> Dict[str, Any]:
        """
        获取优先级报告
        
        Returns:
            优先级信息字典
        """
        result = self.discover()
        
        return {
            "available_paths": {
                level: {
                    "path": str(path),
                    "exists": path.exists()
                }
                for level, path in result.paths.items()
            },
            "priority_order": result.priority_order,
            "override_behavior": (
                "Later paths override earlier paths with the same skill name"
            )
        }


class ConfigurablePathDiscovery(StandardPathDiscovery):
    """
    可配置的路径发现器
    
    允许自定义路径配置
    """
    
    def __init__(
        self,
        user_level: Optional[str] = None,
        project_level: Optional[str] = None,
        extra_paths: Optional[List[str]] = None
    ):
        """
        初始化可配置的路径发现器
        
        Args:
            user_level: 用户级路径 (None 使用默认)
            project_level: 项目级路径 (None 使用默认)
            extra_paths: 额外路径列表
        """
        super().__init__(include_extra=bool(extra_paths))
        
        # 自定义用户级路径
        if user_level:
            self._levels[0] = ("user", "User Level", user_level)
        
        # 自定义项目级路径
        if project_level:
            self._levels[1] = ("project", "Project Level", project_level)
        
        # 添加额外路径
        if extra_paths:
            for i, path in enumerate(extra_paths):
                self._levels.append((f"extra_{i}", f"Extra Path {i}", path))
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ConfigurablePathDiscovery":
        """
        从配置创建实例
        
        Args:
            config: 配置字典
            
        Example:
            config = {
                "user_level": "~/.myapp/skills",
                "project_level": "./.myapp/skills",
                "extra_paths": ["/shared/skills"]
            }
        """
        return cls(
            user_level=config.get("user_level"),
            project_level=config.get("project_level"),
            extra_paths=config.get("extra_paths")
        )


def validate_skill_path(path: str) -> Tuple[bool, str]:
    """
    验证技能路径
    
    Args:
        path: 路径字符串
        
    Returns:
        (是否有效, 错误信息)
    """
    p = Path(os.path.expanduser(path))
    
    # 检查是否是绝对路径
    if not p.is_absolute():
        return False, "Path must be absolute"
    
    # 检查路径遍历攻击
    try:
        resolved = p.resolve()
        if ".." in str(resolved):
            return False, "Path contains parent directory references"
    except Exception:
        return False, "Invalid path"
    
    return True, ""


def normalize_skill_path(path: str) -> str:
    """
    标准化技能路径
    
    Args:
        path: 原始路径
        
    Returns:
        标准化后的路径
    """
    p = Path(os.path.expanduser(path)).resolve()
    return str(p)
