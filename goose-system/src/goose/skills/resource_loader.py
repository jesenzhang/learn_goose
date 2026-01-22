"""
Resource Loader - 技能资源加载器

功能:
- 加载 scripts/ 目录 (可执行文件)
- 解析 requirements.txt 依赖
- 加载 templates/ 目录
- 懒加载 reference.md

Reference: Agent Skills 架构设计手册 - 资源文件结构
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import subprocess
import sys
import os


class ResourceLoader:
    """
    技能资源加载器
    
    处理 L3 执行态的资源文件:
    - scripts/: 可执行脚本
    - templates/: 模板文件
    - reference.md: 静态文档
    - requirements.txt: 依赖声明
    """
    
    def __init__(self, skill_dir: Path):
        """
        初始化资源加载器
        
        Args:
            skill_dir: 技能根目录
        """
        self.skill_dir = skill_dir
        self.scripts_dir = skill_dir / "scripts"
        self.templates_dir = skill_dir / "templates"
        self.reference_md = skill_dir / "reference.md"
        self.requirements_txt = skill_dir / "requirements.txt"
    
    @property
    def has_scripts(self) -> bool:
        """检查是否有 scripts 目录"""
        return self.scripts_dir.exists() and any(
            f.is_file() for f in self.scripts_dir.iterdir()
            if not f.name.startswith(".")
        )
    
    @property
    def has_templates(self) -> bool:
        """检查是否有 templates 目录"""
        return self.templates_dir.exists() and any(
            f.is_file() for f in self.templates_dir.rglob("*")
        )
    
    @property
    def has_reference(self) -> bool:
        """检查是否有 reference.md"""
        return self.reference_md.exists()
    
    @property
    def has_requirements(self) -> bool:
        """检查是否有 requirements.txt"""
        return self.requirements_txt.exists()
    
    def get_scripts(self) -> Dict[str, Path]:
        """
        获取所有脚本文件
        
        Returns:
            {脚本名: 脚本路径}
        """
        scripts = {}
        if self.has_scripts:
            for f in self.scripts_dir.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    scripts[f.name] = f
        return scripts
    
    def get_script_path(self, script_name: str) -> Optional[Path]:
        """
        获取指定脚本的路径
        
        Args:
            script_name: 脚本名称
            
        Returns:
            脚本路径，不存在返回 None
        """
        script_path = self.scripts_dir / script_name
        if script_path.exists() and script_path.is_file():
            return script_path
        return None
    
    def parse_requirements(self) -> List[str]:
        """
        解析 requirements.txt
        
        Returns:
            依赖列表
        """
        if not self.has_requirements:
            return []
        
        requirements = []
        try:
            content = self.requirements_txt.read_text()
            for line in content.splitlines():
                line = line.strip()
                # 跳过注释和空行
                if line and not line.startswith("#"):
                    # 去除版本号（如果有）
                    if ">=" in line:
                        line = line.split(">=")[0].strip()
                    elif "<=" in line:
                        line = line.split("<=")[0].strip()
                    elif "==" in line:
                        line = line.split("==")[0].strip()
                    elif ">" in line:
                        line = line.split(">")[0].strip()
                    elif "<" in line:
                        line = line.split("<")[0].strip()
                    elif "~=" in line:
                        line = line.split("~=")[0].strip()
                    requirements.append(line)
        except Exception:
            pass
        
        return requirements
    
    def install_dependencies(self, verbose: bool = True) -> Dict[str, bool]:
        """
        安装依赖
        
        Args:
            verbose: 是否输出安装信息
            
        Returns:
            {包名: 是否安装成功}
        """
        requirements = self.parse_requirements()
        if not requirements:
            return {}
        
        results = {}
        for pkg in requirements:
            if not pkg:
                continue
                
            try:
                if verbose:
                    print(f"Installing {pkg}...")
                
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True,
                    text=True
                )
                
                results[pkg] = result.returncode == 0
                
                if not results[pkg] and verbose:
                    print(f"  Failed: {result.stderr}")
                    
            except Exception as e:
                if verbose:
                    print(f"  Error installing {pkg}: {e}")
                results[pkg] = False
        
        return results
    
    def get_reference_content(self) -> Optional[str]:
        """
        懒加载 reference.md
        
        Returns:
            reference.md 内容
        """
        if self.has_reference:
            try:
                return self.reference_md.read_text(encoding="utf-8")
            except Exception:
                pass
        return None
    
    def get_template_files(self) -> Dict[str, bytes]:
        """
        获取所有模板文件
        
        Returns:
            {相对路径: 文件内容}
        """
        templates = {}
        if self.has_templates:
            for f in self.templates_dir.rglob("*"):
                if f.is_file():
                    try:
                        rel_path = str(f.relative_to(self.templates_dir))
                        templates[rel_path] = f.read_bytes()
                    except Exception:
                        pass
        return templates
    
    def get_template(self, template_name: str) -> Optional[bytes]:
        """
        获取指定模板
        
        Args:
            template_name: 模板名称或路径
            
        Returns:
            模板内容，不存在返回 None
        """
        template_path = self.templates_dir / template_name
        if template_path.exists() and template_path.is_file():
            try:
                return template_path.read_bytes()
            except Exception:
                pass
        return None
    
    def get_all_resources(self) -> Dict[str, Any]:
        """
        获取所有资源的摘要信息
        
        Returns:
            资源摘要字典
        """
        return {
            "skill_dir": str(self.skill_dir),
            "scripts": {
                "exists": self.has_scripts,
                "files": list(self.get_scripts().keys()),
            },
            "templates": {
                "exists": self.has_templates,
                "count": len(self.get_template_files()),
            },
            "reference": {
                "exists": self.has_reference,
                "size": self.reference_md.stat().st_size if self.has_reference else 0,
            },
            "requirements": {
                "exists": self.has_requirements,
                "packages": self.parse_requirements(),
            },
        }
    
    def collect_for_sandbox(self) -> Dict[str, bytes]:
        """
        收集所有资源用于沙箱挂载
        
        Returns:
            {相对路径: 文件内容}
        """
        resources: Dict[str, bytes] = {}
        
        # 收集脚本
        for name, path in self.get_scripts().items():
            try:
                resources[f"scripts/{name}"] = path.read_bytes()
            except Exception:
                pass
        
        # 收集模板
        for rel_path, content in self.get_template_files().items():
            resources[f"templates/{rel_path}"] = content
        
        # 收集 reference.md
        ref_content = self.get_reference_content()
        if ref_content:
            resources["reference.md"] = ref_content.encode("utf-8")
        
        return resources


class ResourceValidator:
    """
    资源验证器
    
    验证资源文件的安全性
    """
    
    # 禁止的文件模式
    BLOCKED_PATTERNS = [
        ".bat", ".cmd", ".sh",  # 脚本文件 (可能危险)
        ".exe", ".dll", ".so",  # 二进制文件
        ".pyc", ".pyo", "__pycache__",  # Python 缓存
    ]
    
    # 最大文件大小 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    @classmethod
    def validate_script(cls, script_path: Path) -> tuple[bool, str]:
        """
        验证脚本文件
        
        Args:
            script_path: 脚本路径
            
        Returns:
            (是否有效, 错误信息)
        """
        if not script_path.exists():
            return False, "File does not exist"
        
        if not script_path.is_file():
            return False, "Not a file"
        
        # 检查文件大小
        try:
            size = script_path.stat().st_size
            if size > cls.MAX_FILE_SIZE:
                return False, f"File too large ({size} bytes)"
        except Exception:
            pass
        
        # 检查文件扩展名
        suffix = script_path.suffix.lower()
        if suffix in cls.BLOCKED_PATTERNS:
            return False, f"Blocked file type: {suffix}"
        
        return True, ""
    
    @classmethod
    def validate_requirements(cls, requirements: List[str]) -> tuple[bool, List[str]]:
        """
        验证依赖列表
        
        Args:
            requirements: 依赖列表
            
        Returns:
            (是否有效, 警告列表)
        """
        warnings = []
        
        for req in requirements:
            # 检查是否有危险的包
            if req.lower() in {"os", "sys", "subprocess", "shutil"}:
                warnings.append(f"Package '{req}' may require special handling")
        
        return len(warnings) == 0, warnings
