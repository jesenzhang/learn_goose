"""
Skills Platform Extension (MCP Server)

将 Skills 功能实现为 MCP Platform Extension，参考 goose-rs skills_extension.rs

功能：
- 自动发现 Skills (~/.claude/skills, ./.claude/skills 等)
- 提供 loadSkill 工具
- 生成系统提示包含可用 Skills 列表

Reference: goose-rs/crates/goose/src/agents/skills_extension.rs
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
import re

from ...session import SessionManager
from ...skills import (
    Skill,
    SkillLoader,
    SkillRegistry,
    SkillMetadata,
    ProgressiveDisclosureStateMachine,
    SkillState,
)


@dataclass
class SkillInfo:
    """技能信息"""
    name: str
    description: str
    body: str = ""
    directory: str = ""
    supporting_files: List[str] = field(default_factory=list)


class SkillsMcpServer:
    """
    Skills MCP Server Platform Extension
    
    作为 MCP Server 实现，提供：
    - list_tools: 列出 loadSkill 工具
    - call_tool: 加载并返回技能内容
    """
    
    EXTENSION_NAME = "skills"
    
    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        skill_directories: Optional[List[str]] = None
    ):
        self.session_manager = session_manager
        self.skill_directories = skill_directories or self._get_default_skill_directories()
        self.skills: Dict[str, SkillInfo] = {}
        self.skill_loader = SkillLoader()
        self.state_machine = ProgressiveDisclosureStateMachine()
        self._initialized = False
    
    def _get_default_skill_directories(self) -> List[str]:
        """获取默认技能目录"""
        dirs = []
        
        # 用户级别
        import os
        home = os.path.expanduser("~")
        dirs.append(os.path.join(home, ".claude", "skills"))
        dirs.append(os.path.join(home, ".config", "agents", "skills"))
        
        # 工作目录级别
        cwd = os.getcwd() if hasattr(os, 'getcwd') else "."
        dirs.append(os.path.join(cwd, ".claude", "skills"))
        dirs.append(os.path.join(cwd, ".goose", "skills"))
        dirs.append(os.path.join(cwd, ".agents", "skills"))
        
        return dirs
    
    async def initialize(self) -> Dict[str, Any]:
        """初始化并发现技能"""
        self._discover_skills()
        
        instructions = self._generate_instructions()
        
        self._initialized = True
        
        return {
            "name": self.EXTENSION_NAME,
            "version": "1.0.0",
            "description": "Load and use skills from relevant directories",
            "instructions": instructions,
        }
    
    def _discover_skills(self) -> None:
        """发现所有技能"""
        self.skills = {}
        
        for dir_path in self.skill_directories:
            dir_obj = Path(dir_path)
            if not dir_obj.exists():
                continue
            
            try:
                for entry in dir_obj.iterdir():
                    if not entry.is_dir():
                        continue
                    
                    skill_file = entry / "SKILL.md"
                    if not skill_file.exists():
                        continue
                    
                    skill_info = self._parse_skill(entry, skill_file)
                    if skill_info:
                        # 后面的目录覆盖前面的同名技能
                        self.skills[skill_info.name] = skill_info
            except Exception:
                continue
    
    def _parse_skill(self, skill_dir: Path, skill_file: Path) -> Optional[SkillInfo]:
        """解析技能文件"""
        try:
            content = skill_file.read_text(encoding="utf-8")
            
            # 解析 frontmatter
            frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
            match = re.match(frontmatter_pattern, content, re.DOTALL)
            
            if not match:
                return None
            
            yaml_content = match.group(1)
            lines = yaml_content.strip().split("\n")
            metadata = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()
            
            name = metadata.get("name", "")
            description = metadata.get("description", "")
            
            if not name or not description:
                return None
            
            # 获取 body
            body_start = match.end()
            body = content[body_start:].strip()
            
            # 获取支持文件
            supporting_files = []
            if skill_dir.is_dir():
                for f in skill_dir.iterdir():
                    if f.is_file() and f.name != "SKILL.md":
                        supporting_files.append(f.name)
            
            return SkillInfo(
                name=name,
                description=description,
                body=body,
                directory=str(skill_dir),
                supporting_files=supporting_files
            )
        except Exception:
            return None
    
    def _generate_instructions(self) -> str:
        """生成系统提示"""
        if not self.skills:
            return ""
        
        lines = [
            "You have these skills at your disposal, when it is clear they can help you solve a problem or you are asked to use them:",
            ""
        ]
        
        for name in sorted(self.skills.keys()):
            skill = self.skills[name]
            lines.append(f"- {name}: {skill.description}")
        
        return "\n".join(lines)
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出可用工具"""
        if not self._initialized:
            await self.initialize()
        
        if not self.skills:
            return []
        
        return [{
            "name": "loadSkill",
            "description": "Load a skill by name and return its content. Use this tool when you need to use a specific skill.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the skill to load"
                    }
                },
                "required": ["name"]
            }
        }]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        if name != "loadSkill":
            return {"error": f"Unknown tool: {name}"}
        
        skill_name = arguments.get("name")
        if not skill_name:
            return {"error": "Missing required parameter: name"}
        
        if skill_name not in self.skills:
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self.skills[skill_name]
        
        # 生成响应
        response_parts = [
            f"# Skill: {skill.name}",
            "",
            skill.body,
            ""
        ]
        
        if skill.supporting_files:
            response_parts.extend([
                "## Supporting Files",
                f"Skill directory: {skill.directory}",
                "",
                "The following supporting files are available:",
            ])
            for f in skill.supporting_files:
                response_parts.append(f"- {f}")
            response_parts.append("")
            response_parts.append("Use the view file tools to access these files as needed.")
        
        return {
            "content": [{
                "type": "text",
                "text": "\n".join(response_parts)
            }]
        }
    
    def get_skill_names(self) -> List[str]:
        """获取所有技能名称"""
        return list(self.skills.keys())
    
    def get_skill(self, name: str) -> Optional[SkillInfo]:
        """获取指定技能"""
        return self.skills.get(name)


class SkillsPlatformExtension:
    """
    Skills Platform Extension for Agent
    
    将 SkillsMcpServer 集成到 Agent 的插件系统中
    """
    
    EXTENSION_NAME = "skills"
    
    def __init__(self):
        self.server: Optional[SkillsMcpServer] = None
        self._connected = False
    
    async def initialize(self, session_manager: Optional[SessionManager] = None) -> Dict[str, Any]:
        """初始化"""
        self.server = SkillsMcpServer(session_manager=session_manager)
        return await self.server.initialize()
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出工具"""
        if not self.server:
            return []
        return await self.server.list_tools()
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        if not self.server:
            return {"error": "Extension not initialized"}
        return await self.server.call_tool(name, arguments)
    
    async def close(self) -> None:
        """关闭"""
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected


def create_skills_extension(session_manager: Optional[SessionManager] = None) -> SkillsPlatformExtension:
    """创建 Skills Platform Extension"""
    ext = SkillsPlatformExtension()
    return ext
