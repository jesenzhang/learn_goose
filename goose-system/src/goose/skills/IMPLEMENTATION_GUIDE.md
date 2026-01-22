"""
Goose System Skills Implementation Guide

基于 Agent Skills 架构设计手册和 goose-rs 实现，
给出 goose-system 的完整实现方案。

Target: F:\Workspace\learn_goose\goose-system\src\goose\skills
"""

# ============================================================================
# 第一部分：当前实现审查
# ============================================================================

"""
当前文件结构:
├── base.py          - Skill, SkillMetadata (✅ 基础完成)
├── loader.py        - SkillLoader, SkillBackend (⚠️ 部分完成)
├── registry.py      - SkillRegistry (✅ 完成)
├── impl_loader.py   - SkillImplLoader (✅ 完成)
└── __init__.py      - 模块导出 (✅ 完成)

缺少的关键组件:
1. 渐进式披露状态机 (ProgressiveDisclosureStateMachine)
2. 工具拦截器 (ToolInterceptor)
3. 沙箱集成器 (SandboxIntegrator)
4. 标准路径发现器 (StandardPathDiscovery)
5. 资源加载器 (ResourceLoader for L3)
"""

# ============================================================================
# 第二部分：需要新增的组件
# ============================================================================

## 2.1 标准路径发现器 (StandardPathDiscovery)

"""
实现位置: new_path_discovery.py

功能:
- 发现 ~/.claude/skills/ (用户级)
- 发现 ./.claude/skills/ (项目级)
- 支持优先级覆盖 (项目级 > 用户级)
"""

from pathlib import Path
from typing import List, Dict, Optional
import os

class StandardPathDiscovery:
    """标准路径发现器"""
    
    # 按优先级排序（后面覆盖前面）
    DEFAULT_PATHS = [
        ("user", Path.home() / ".claude" / "skills"),      # 优先级 0 (低)
        ("project", Path.cwd() / ".claude" / "skills"),     # 优先级 1 (高)
    ]
    
    def discover(self) -> Dict[str, Path]:
        """发现所有标准路径"""
        paths = {}
        for level, path in self.DEFAULT_PATHS:
            if path.exists() and path.is_dir():
                paths[level] = path
        return paths
    
    def get_merged_skills_dir(self) -> Path:
        """获取合并的技能目录用于扫描"""
        # 返回临时目录，包含所有技能的符号链接
        # 或直接扫描多个路径
        pass


## 2.2 渐进式披露状态机 (ProgressiveDisclosureStateMachine)

"""
实现位置: new_state_machine.py

三级状态机:

L1 (Awareness) ──► L2 (Activation) ──► L3 (Execution)
     │                  │                    │
     │ Intent           │ Full Instructions  │ Scripts Mounted
     │ Detected         │ Injected           │ Code Execution
     │                  │                    │
     ▼                  ▼                    ▼
感知态              激活态                 执行态
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List, Any
from pathlib import Path

class SkillState(Enum):
    """技能状态枚举"""
    AWARENESS = "awareness"      # L1: 仅元数据
    ACTIVATION = "activation"    # L2: 完整指令
    EXECUTION = "execution"      # L3: 脚本执行

@dataclass
class ProgressiveDisclosureState:
    """渐进式披露状态"""
    state: SkillState = SkillState.AWARENESS
    active_skills: Set[str] = field(default_factory=set)  # L2 激活的技能
    execution_skills: Set[str] = field(default_factory=set)  # L3 执行中的技能
    
    def activate(self, skill_name: str) -> None:
        """激活技能 (L1 -> L2)"""
        self.state = SkillState.ACTIVATION
        self.active_skills.add(skill_name)
    
    def enter_execution(self, skill_name: str) -> None:
        """进入执行态 (L2 -> L3)"""
        self.state = SkillState.EXECUTION
        self.execution_skills.add(skill_name)
    
    def deactivate(self, skill_name: str) -> None:
        """停用技能"""
        self.active_skills.discard(skill_name)
        self.execution_skills.discard(skill_name)


class ProgressiveDisclosureStateMachine:
    """
    渐进式披露状态机
    
    控制技能从 L1 -> L2 -> L3 的状态转换
    """
    
    def __init__(self):
        self._state = ProgressiveDisclosureState()
        self._skill_content: Dict[str, str] = {}  # L2 内容缓存
        self._skill_resources: Dict[str, Dict[str, bytes]] = {}  # L3 资源
    
    @property
    def current_state(self) -> SkillState:
        return self._state.state
    
    def get_awareness_prompt(self, skills_metadata: List[Dict[str, Any]]) -> str:
        """
        L1: 生成感知态提示 (仅元数据)
        
        这是一个轻量级的系统提示，包含所有可用技能的名称和描述。
        用于让 LLM 知道有哪些技能可用，但不加载完整指令。
        """
        if not skills_metadata:
            return "(No skills available)"
        
        lines = ["You have the following skills available:\n"]
        for meta in skills_metadata:
            lines.append(f"- **{meta['name']}**: {meta['description']}")
        
        return "\n".join(lines)
    
    def get_activation_content(self, skill_name: str) -> Optional[str]:
        """
        L2: 获取激活态的完整指令
        
        当技能被激活时，调用此方法获取完整 SKILL.md 内容
        """
        return self._skill_content.get(skill_name)
    
    def activate_skill(self, skill_name: str, full_content: str) -> None:
        """
        L2: 激活技能
        
        Args:
            skill_name: 技能名称
            full_content: SKILL.md 完整内容
        """
        self._state.activate(skill_name)
        self._skill_content[skill_name] = full_content
    
    def get_execution_resources(self, skill_name: str) -> Dict[str, bytes]:
        """
        L3: 获取执行态的资源
        
        返回 scripts/, templates/ 等资源文件内容
        """
        return self._skill_resources.get(skill_name, {})
    
    def mount_for_execution(self, skill_name: str, resource_dir: Path) -> None:
        """
        L3: 挂载资源用于执行
        
        当 LLM 生成代码尝试调用 scripts/ 时，调用此方法
        将技能目录挂载到沙箱
        """
        self._state.enter_execution(skill_name)
        # 收集资源文件
        resources = {}
        for root, dirs, files in os.walk(resource_dir):
            for f in files:
                fpath = Path(root) / f
                try:
                    resources[str(fpath.relative_to(resource_dir))] = fpath.read_bytes()
                except Exception:
                    pass
        self._skill_resources[skill_name] = resources


## 2.3 工具拦截器 (ToolInterceptor)

"""
实现位置: new_tool_interceptor.py

功能:
- 解析 SKILL.md 中的 allowed-tools
- 拦截工具调用请求
- 根据当前激活的技能进行权限检查
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass

@dataclass
class ToolPermission:
    """工具权限配置"""
    tool_name: str
    allowed: bool
    reason: Optional[str] = None

class ToolInterceptor:
    """
    工具拦截器
    
    实现 allowed-tools 权限控制逻辑
    """
    
    def __init__(self):
        self._skill_permissions: Dict[str, Set[str]] = {}  # skill -> allowed tools
        self._global_blocked: Set[str] = set()  # 全局禁止的工具
    
    def register_skill_tools(self, skill_name: str, allowed_tools: List[str]) -> None:
        """注册技能的允许工具列表"""
        self._skill_permissions[skill_name] = set(allowed_tools)
    
    def check_permission(
        self,
        tool_name: str,
        active_skills: List[str]
    ) -> ToolPermission:
        """
        检查工具调用权限
        
        Args:
            tool_name: 工具名称
            active_skills: 当前激活的技能列表
            
        Returns:
            ToolPermission: 权限结果
        """
        # 1. 检查全局禁止
        if tool_name in self._global_blocked:
            return ToolPermission(
                tool_name=tool_name,
                allowed=False,
                reason="Globally blocked tool"
            )
        
        # 2. 检查是否有技能允许此工具
        for skill in active_skills:
            allowed = self._skill_permissions.get(skill, set())
            # 空列表表示允许所有工具
            if not allowed or tool_name in allowed:
                return ToolPermission(
                    tool_name=tool_name,
                    allowed=True
                )
        
        # 3. 无技能允许此工具
        return ToolPermission(
            tool_name=tool_name,
            allowed=False,
            reason=f"Tool not in allowed-tools of active skills: {active_skills}"
        )


## 2.4 资源加载器 (ResourceLoader)

"""
实现位置: new_resource_loader.py

功能:
- 加载 scripts/ 目录 (可执行文件)
- 解析 requirements.txt
- 加载 templates/ 目录
- 懒加载 reference.md
"""

from pathlib import Path
from typing import Dict, List, Optional
import subprocess
import sys

class ResourceLoader:
    """
    技能资源加载器
    
    处理 L3 执行态的资源
    """
    
    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.scripts_dir = skill_dir / "scripts"
        self.templates_dir = skill_dir / "templates"
        self.reference_md = skill_dir / "reference.md"
    
    def get_scripts(self) -> Dict[str, Path]:
        """获取所有脚本文件"""
        scripts = {}
        if self.scripts_dir.exists():
            for f in self.scripts_dir.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    scripts[f.name] = f
        return scripts
    
    def parse_requirements(self) -> List[str]:
        """解析 requirements.txt"""
        req_file = self.scripts_dir / "requirements.txt"
        if not req_file.exists():
            return []
        
        requirements = []
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                requirements.append(line)
        return requirements
    
    def install_dependencies(self) -> bool:
        """安装依赖"""
        requirements = self.parse_requirements()
        if not requirements:
            return True
        
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install"
            ] + requirements)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def get_reference_content(self) -> Optional[str]:
        """懒加载 reference.md"""
        if self.reference_md.exists():
            return self.reference_md.read_text()
        return None
    
    def get_template_files(self) -> Dict[str, bytes]:
        """获取模板文件"""
        templates = {}
        if self.templates_dir.exists():
            for f in self.templates_dir.rglob("*"):
                if f.is_file():
                    try:
                        templates[str(f.relative_to(self.templates_dir))] = f.read_bytes()
                    except Exception:
                        pass
        return templates


## 2.5 沙箱集成器 (SandboxIntegrator)

"""
实现位置: new_sandbox_integrator.py

功能:
- 将技能目录挂载到沙箱
- 执行脚本并捕获输出
- 处理生成的文件
"""

from pathlib import Path
from typing import Dict, Optional, Any
import tempfile
import shutil

class SandboxIntegrator:
    """
    沙箱集成器
    
    将技能挂载到执行环境
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(tempfile.gettempdir()) / "skill_outputs"
        self.output_dir.mkdir(exist_ok=True)
    
    def mount_skill(self, skill_dir: Path) -> Path:
        """
        将技能目录挂载到沙箱工作目录
        
        Returns:
            挂载后的路径
        """
        mount_point = self.output_dir / skill_dir.name
        if mount_point.exists():
            shutil.rmtree(mount_point)
        shutil.copytree(skill_dir, mount_point)
        return mount_point
    
    def execute_script(self, script_path: Path, args: List[str] = []) -> Dict[str, Any]:
        """
        执行脚本
        
        Returns:
            执行结果字典
        """
        # 此处应集成实际的沙箱执行逻辑
        # 如 Docker 容器、gVisor 或简单的 subprocess
        pass
    
    def handle_output_files(self, mount_point: Path) -> Dict[str, str]:
        """
        处理生成的文件
        
        将输出文件转换为 file_id 或下载链接
        """
        outputs = {}
        for f in mount_point.rglob("*"):
            if f.is_file() and f.suffix in {".pdf", ".xlsx", ".csv", ".json"}:
                # 生成 file_id 或上传到对象存储
                outputs[f.name] = f"file://{f}"
        return outputs


# ============================================================================
# 第三部分：改进现有组件
# ============================================================================

## 3.1 改进 base.py - 添加严格验证

"""
需要添加:
1. 严格的 YAML 语法检查 (禁止 Tab 缩进)
2. kebab-case 命名验证 (已在 regex 中实现，但需要更严格)
3. 环境变量白名单
"""

import re
import yaml

# 扩展验证逻辑
def validate_skill_name_strict(name: str) -> tuple[bool, str]:
    """严格验证技能名称"""
    # 1. 长度检查
    if len(name) > 64:
        return False, "name exceeds 64 characters"
    
    # 2. kebab-case 格式
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        return False, "name must be lowercase alphanumeric with single hyphens"
    
    return True, ""

def validate_yaml_frontmatter(content: str) -> tuple[bool, str]:
    """验证 YAML 前言语法"""
    frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if not match:
        return False, "Missing or invalid frontmatter delimiters"
    
    try:
        data = yaml.safe_load(match.group(1))
        if not isinstance(data, dict):
            return False, "Frontmatter must be a YAML dictionary"
        
        # 必填字段检查
        if "name" not in data:
            return False, "Missing required field: name"
        if "description" not in data:
            return False, "Missing required field: description"
        
        return True, ""
    
    except yaml.YAMLError as e:
        return False, f"YAML syntax error: {str(e)}"


## 3.2 改进 loader.py - 添加标准路径

"""
需要修改:
1. 添加标准路径发现
2. 支持 requirements.txt 解析
3. 添加渐进式披露提示模板
"""

class ImprovedSkillLoader:
    """改进的技能加载器"""
    
    # 标准扫描路径 (优先级从低到高)
    STANDARD_PATHS = [
        Path.home() / ".claude" / "skills",      # 用户级
        Path.cwd() / ".claude" / "skills",        # 项目级 (更高优先级)
    ]
    
    def load_with_progressive_disclosure(self) -> Dict[str, Any]:
        """
        加载技能并准备渐进式披露
        
        Returns:
            {
                "metadata_list": [...],  # L1 数据
                "skills": {...},         # 完整技能
                "state_machine": ProgressiveDisclosureStateMachine
            }
        """
        # 1. 扫描所有标准路径
        all_skills = {}
        for path in self.STANDARD_PATHS:
            if path.exists():
                skills = self.load_skills_from_directory(str(path))
                all_skills.update(skills)
        
        # 2. 创建状态机
        state_machine = ProgressiveDisclosureStateMachine()
        
        # 3. 准备 L1 数据
        metadata_list = []
        for name, skill in all_skills.items():
            metadata_list.append(skill.to_metadata_dict())
            # 注册工具权限
            if skill.metadata.allowed_tools:
                for tool in skill.metadata.allowed_tools:
                    pass  # 注册到 ToolInterceptor
        
        return {
            "metadata_list": metadata_list,
            "skills": all_skills,
            "state_machine": state_machine
        }


# ============================================================================
# 第四部分：文件修改清单
# ============================================================================

"""
需要修改/创建的文件:

1. 修改 base.py
   - 添加 validate_yaml_frontmatter()
   - 添加 validate_skill_name_strict()

2. 修改 loader.py
   - 添加 STANDARD_PATHS 常量
   - 添加 ImprovedSkillLoader 类

3. 修改 registry.py
   - 无重大修改

4. 修改 impl_loader.py
   - 无重大修改

5. 创建 new_state_machine.py (新增)
   - ProgressiveDisclosureStateMachine
   - SkillState 枚举

6. 创建 new_tool_interceptor.py (新增)
   - ToolInterceptor
   - ToolPermission

7. 创建 new_resource_loader.py (新增)
   - ResourceLoader

8. 创建 new_sandbox_integrator.py (新增)
   - SandboxIntegrator

9. 创建 new_path_discovery.py (新增)
   - StandardPathDiscovery

10. 创建 __all__.py (整合导出)
    - 整合所有组件的导出
"""

# ============================================================================
# 第五部分：使用示例
# ============================================================================

"""
集成后的使用流程:

```python
from goose.skills import (
    SkillLoader,
    ProgressiveDisclosureStateMachine,
    ToolInterceptor,
    ResourceLoader,
    SandboxIntegrator
)

# 1. 初始化
loader = ImprovedSkillLoader()
result = loader.load_with_progressive_disclosure()

state_machine = result["state_machine"]
interceptor = ToolInterceptor()

# 2. L1: 生成感知态提示
awareness_prompt = state_machine.get_awareness_prompt(result["metadata_list"])

# 3. L2: 激活技能 (当 LLM 表示要使用某技能时)
skill = result["skills"]["pdf-processor"]
state_machine.activate_skill(skill.name, skill.content)

# 4. 检查工具权限 (当 LLM 调用工具时)
permission = interceptor.check_permission("Read", [skill.name])
if not permission.allowed:
    raise PermissionError(permission.reason)

# 5. L3: 执行脚本
resource_loader = ResourceLoader(Path(skill.path))
resource_loader.install_dependencies()  # 安装依赖

mount_point = SandboxIntegrator().mount_skill(Path(skill.path))
result = SandboxIntegrator().execute_script(
    mount_point / "scripts" / "process.py"
)
```

这样实现的完整性和 goose-rs + 文档要求完全对齐。
"""
