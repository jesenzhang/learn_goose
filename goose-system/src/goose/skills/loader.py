"""
Skill Loader

Skill 加载器，支持多源加载和渐进式披露。
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
import os
import re

from .base import Skill, SkillMetadata, parse_skill_metadata


class SkillBackend:
    """Skill 后端协议（抽象基类）"""
    
    def ls_info(self, path: str) -> List[Dict[str, Any]]:
        """列出目录内容"""
        return []
    
    def download_files(self, paths: List[str]) -> Dict[str, bytes]:
        """下载文件"""
        return {}


class FilesystemBackend(SkillBackend):
    """文件系统后端"""
    
    def ls_info(self, path: str) -> List[Dict[str, Any]]:
        """列出目录内容"""
        items = []
        p = Path(path)
        
        if not p.exists() or not p.is_dir():
            return items
        
        for item in p.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                items.append({
                    "path": str(item),
                    "is_dir": True,
                    "has_skill_file": skill_md.exists()
                })
        
        return items
    
    def download_files(self, paths: List[str]) -> Dict[str, bytes]:
        """下载文件"""
        files = {}
        for path in paths:
            p = Path(path)
            if p.exists() and p.is_file():
                try:
                    files[path] = p.read_bytes()
                except Exception:
                    pass
        return files


class MemoryBackend(SkillBackend):
    """内存后端（用于测试）"""
    
    def __init__(self):
        self.files: Dict[str, bytes] = {}
    
    def upload_files(self, files: List[tuple[str, bytes]]) -> None:
        """上传文件"""
        for path, content in files:
            self.files[path] = content
    
    def ls_info(self, path: str) -> List[Dict[str, Any]]:
        """列出目录内容"""
        items = []
        prefix = path.rstrip("/") + "/"
        
        for file_path in self.files.keys():
            if file_path.startswith(prefix) and len(file_path) > len(prefix):
                relative = file_path[len(prefix):]
                if "/" not in relative:
                    items.append({
                        "path": file_path,
                        "is_dir": False,
                        "size": len(self.files[file_path])
                    })
        
        return items
    
    def download_files(self, paths: List[str]) -> Dict[str, bytes]:
        """下载文件"""
        return {path: self.files[path] for path in paths if path in self.files}


class SkillLoader:
    """
    Skill 加载器
    
    支持从多个源加载 Skill，实现渐进式披露模式。
    """
    
    def __init__(self, backend: Optional[SkillBackend] = None):
        self.backend = backend or FilesystemBackend()
    
    def load_skill(self, skill_path: str) -> Skill:
        """
        加载单个 Skill
        
        Args:
            skill_path: Skill 路径（目录或 SKILL.md 文件）
            
        Returns:
            Skill: 加载的 Skill
        """
        p = Path(skill_path)
        
        # 如果是目录，查找 SKILL.md
        if p.is_dir():
            skill_file = p / "SKILL.md"
            if not skill_file.exists():
                raise FileNotFoundError(f"SKILL.md not found in {skill_path}")
            content = skill_file.read_text(encoding="utf-8")
            path = str(skill_file)
        else:
            content = p.read_text(encoding="utf-8")
            path = str(p)
        
        # 解析元数据
        metadata = parse_skill_metadata(content, path)
        if metadata is None:
            raise ValueError(f"Invalid skill metadata in {skill_path}")
        
        # 验证名称
        is_valid, error = metadata.validate()
        if not is_valid:
            raise ValueError(f"Invalid skill name: {error}")
        
        return Skill(metadata, content)
    
    def load_skills_from_directory(self, directory: str) -> List[Skill]:
        """
        从目录加载所有 Skills
        
        Args:
            directory: 目录路径
            
        Returns:
            List[Skill]: 加载的 Skills 列表
        """
        skills = []
        items = self.backend.ls_info(directory)
        
        skill_dirs = [item for item in items if item.get("is_dir")]
        
        for item in skill_dirs:
            skill_dir = item["path"]
            try:
                skill = self.load_skill(skill_dir)
                skills.append(skill)
            except Exception as e:
                print(f"Warning: Failed to load skill from {skill_dir}: {e}")
        
        return skills
    
    def load_skills_from_sources(
        self,
        sources: List[str],
        override: bool = True
    ) -> Dict[str, Skill]:
        """
        从多个源加载 Skills（后面的覆盖前面的）
        
        Args:
            sources: 源路径列表
            override: 是否允许覆盖
            
        Returns:
            Dict[str, Skill]: 加载的 Skills（按名称索引）
        """
        all_skills: Dict[str, Skill] = {}
        
        for source_path in sources:
            skills = self.load_skills_from_directory(source_path)
            for skill in skills:
                if skill.name in all_skills:
                    if override:
                        print(f"Warning: Overriding skill '{skill.name}'")
                    else:
                        continue
                all_skills[skill.name] = skill
        
        return all_skills
    
    def create_skill_file(
        self,
        name: str,
        description: str,
        content: str,
        output_dir: str,
        license: str = "MIT",
        allowed_tools: Optional[List[str]] = None
    ) -> str:
        """
        创建 Skill 文件
        
        Args:
            name: Skill 名称
            description: 描述
            content: 完整内容（Markdown）
            output_dir: 输出目录
            license: 许可证
            allowed_tools: 允许的工具列表
            
        Returns:
            str: 创建的文件路径
        """
        # 验证名称
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
            raise ValueError(f"Invalid skill name: {name}")
        
        # 构建前言
        frontmatter = f"""---
name: {name}
description: {description}
license: {license}
"""

        if allowed_tools:
            frontmatter += f"allowed-tools: {' '.join(allowed_tools)}\n"

        frontmatter += f"""---
{content}
"""
        
        # 创建目录和文件
        skill_dir = Path(output_dir) / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(frontmatter, encoding="utf-8")
        
        return str(skill_file)


# =============================================================================
# Skill System Prompt Template
# =============================================================================
SKILLS_SYSTEM_PROMPT = """
## Skills System

You have access to a skills library providing specialized capabilities and domain knowledge.

**Available Skills:**

{skills_list}

**How to Use Skills (Progressive Disclosure):**

Skills follow a **progressive disclosure** pattern:

1. **Recognition**: Check if task matches a skill's description
2. **Reading**: Use the path to read full SKILL.md instructions
3. **Execution**: Follow the skill's step-by-step workflows
4. **Support**: Access helper scripts in skill directory

**When to Use Skills:**
- Task matches skill's domain (e.g., "research X" → web-research)
- Need structured workflows for complex tasks
- Skill provides proven patterns and best practices
"""


def format_skills_for_prompt(skills: Dict[str, Skill]) -> str:
    """格式化 Skills 用于系统提示"""
    if not skills:
        return "(No skills available)"
    
    lines = []
    for skill in skills.values():
        lines.append(f"- **{skill.name}**: {skill.description}")
        if skill.metadata.allowed_tools:
            lines.append(f"  -> Allowed tools: {', '.join(skill.metadata.allowed_tools)}")
        lines.append(f"  -> Read `{skill.path}` for full instructions")
    
    return "\n".join(lines)
