# Goose System Skills 实现完整指南

## 一、分析结论

### 当前实现状态

| 组件 | 文件 | 状态 | 评分 |
|------|------|------|------|
| Skill 数据模型 | `base.py` | ✅ 基础完成 | 80% |
| 技能加载器 | `loader.py` | ⚠️ 部分完成 | 60% |
| 技能注册表 | `registry.py` | ✅ 完整 | 95% |
| 实现加载器 | `impl_loader.py` | ✅ 完整 | 90% |

### 缺失的关键功能

根据 Agent Skills 架构设计手册和 goose-rs 实现，缺失以下功能：

```
❌ 1. 三级渐进式披露状态机
   - L1 (Awareness): 仅元数据
   - L2 (Activation): 完整指令
   - L3 (Execution): 脚本执行

❌ 2. 工具拦截器 (ToolInterceptor)
   - allowed-tools 权限控制
   - 工具调用前拦截鉴权

❌ 3. 标准路径发现器
   - ~/.claude/skills/ (用户级)
   - ./.claude/skills/ (项目级)

❌ 4. 资源加载器
   - scripts/ 目录支持
   - requirements.txt 解析
   - reference.md 懒加载

❌ 5. 沙箱集成器
   - 脚本挂载
   - 依赖安装
   - 输出文件处理
```

---

## 二、需要新增的文件

### 文件清单

```
goose-system/src/goose/skills/
├── __init__.py                    # 修改：导出新增组件
├── base.py                        # 修改：添加严格验证
├── loader.py                      # 修改：添加标准路径
├── registry.py                    # 修改：添加状态机集成
├── impl_loader.py                 # 修改：修复 goose 引用
├── state_machine.py               # 新增：渐进式披露状态机
├── tool_interceptor.py            # 新增：工具拦截器
├── resource_loader.py             # 新增：资源加载器 (L3)
├── sandbox_integrator.py          # 新增：沙箱集成器
└── path_discovery.py              # 新增：标准路径发现器
```

---

## 三、核心组件实现

### 3.1 渐进式披露状态机 (state_machine.py)

```python
class SkillState(Enum):
    AWARENESS = "awareness"    # L1
    ACTIVATION = "activation"  # L2
    EXECUTION = "execution"    # L3

class ProgressiveDisclosureStateMachine:
    """三级状态机 - Token 优化核心"""
    
    def get_awareness_prompt(self, metadata_list) -> str:
        """L1: 仅名称和描述"""
        
    def activate_skill(self, name: str, content: str) -> None:
        """L2: 激活技能，注入完整指令"""
        
    def enter_execution(self, name: str, resource_dir: Path) -> None:
        """L3: 挂载脚本资源"""
```

### 3.2 工具拦截器 (tool_interceptor.py)

```python
class ToolInterceptor:
    """allowed-tools 权限控制"""
    
    GLOBAL_BLOCKED_TOOLS = {
        "Bash", "Shell", "Delete", "System", ...
    }
    
    def check_permission(self, tool_name: str, active_skills: List[str]) -> ToolPermission:
        """检查工具调用权限"""
        
    def register_skill_tools(self, skill_name: str, allowed_tools: List[str]) -> None:
        """注册技能允许的工具列表"""
```

### 3.3 资源加载器 (resource_loader.py)

```python
class ResourceLoader:
    """L3 执行态资源加载"""
    
    def parse_requirements(self) -> List[str]:
        """解析 requirements.txt"""
        
    def install_dependencies(self) -> bool:
        """安装依赖"""
        
    def get_reference_content(self) -> Optional[str]:
        """懒加载 reference.md"""
```

---

## 四、集成使用示例

```python
from goose.skills import (
    SkillLoader,
    ProgressiveDisclosureStateMachine,
    ToolInterceptor,
    ResourceLoader,
    SandboxIntegrator
)

# 1. 初始化组件
loader = SkillLoader()
state_machine = ProgressiveDisclosureStateMachine()
interceptor = ToolInterceptor()
sandbox = SandboxIntegrator()

# 2. 加载技能
skills = loader.load_skills_from_sources([
    "~/.claude/skills",
    "./.claude/skills"
])

# 3. L1: 生成感知态提示
metadata_list = [s.to_metadata_dict() for s in skills.values()]
awareness_prompt = state_machine.get_awareness_prompt(metadata_list)

# 4. L2: 激活技能
skill = skills["pdf-processor"]
state_machine.activate_skill(skill.name, skill.content)
interceptor.register_skill_tools(skill.name, skill.metadata.allowed_tools)

# 5. 检查工具权限
permission = interceptor.check_permission("Read", [skill.name])
if not permission.allowed:
    raise PermissionError(permission.reason)

# 6. L3: 执行脚本
resource_loader = ResourceLoader(Path(skill.path))
resource_loader.install_dependencies()
state_machine.enter_execution(skill.name, Path(skill.path))

# 7. 沙箱执行
mount_point = sandbox.mount_skill(Path(skill.path))
result = sandbox.execute_script(mount_point / "scripts" / "process.py")
```

---

## 五、测试用例

参考 Agent Skills 运行时验收测试手册，需要添加以下测试：

```python
# test_state_machine.py
class TestProgressiveDisclosure(unittest.TestCase):
    def test_l1_metadata_only(self):
        """TC-04: 初始状态仅加载元数据"""
        
    def test_l2_activation(self):
        """TC-05: 激活后加载完整指令"""
        
# test_tool_interceptor.py
class TestSecurity(unittest.TestCase):
    def test_tool_blocking(self):
        """TC-07: 验证非白名单工具被拦截"""
        
# test_path_discovery.py
class TestDiscovery(unittest.TestCase):
    def test_standard_paths(self):
        """验证标准路径发现"""
```

---

## 六、文件修改详情

### 6.1 修改 `__init__.py`

```python
from .base import Skill, SkillMetadata, parse_skill_metadata
from .loader import SkillLoader, FilesystemBackend, MemoryBackend
from .registry import SkillRegistry, SkillInfo
from .impl_loader import SkillImplLoader, load_skill_with_implementation
from .state_machine import ProgressiveDisclosureStateMachine, SkillState
from .tool_interceptor import ToolInterceptor, ToolPermission
from .resource_loader import ResourceLoader
from .sandbox_integrator import SandboxIntegrator
from .path_discovery import StandardPathDiscovery

__all__ = [
    # 原有
    "Skill", "SkillMetadata", "parse_skill_metadata",
    "SkillLoader", "FilesystemBackend", "MemoryBackend",
    "SkillRegistry", "SkillInfo",
    "SkillImplLoader", "load_skill_with_implementation",
    # 新增
    "ProgressiveDisclosureStateMachine", "SkillState",
    "ToolInterceptor", "ToolPermission",
    "ResourceLoader",
    "SandboxIntegrator",
    "StandardPathDiscovery",
]
```

### 6.2 修改 `loader.py`

添加标准路径：

```python
class ImprovedSkillLoader:
    STANDARD_PATHS = [
        Path.home() / ".claude" / "skills",      # 用户级
        Path.cwd() / ".claude" / "skills",        # 项目级
    ]
    
    def load_with_progressive_disclosure(self) -> Dict[str, Any]:
        """加载并准备渐进式披露"""
        ...
```

### 6.3 修改 `base.py`

添加严格验证：

```python
def validate_yaml_frontmatter(content: str) -> tuple[bool, str]:
    """验证 YAML 前言语法"""
    ...

def validate_skill_name_strict(name: str) -> tuple[bool, str]:
    """严格验证技能名称"""
    ...
```

---

## 七、优先级排序

### 第一优先级 (必须实现)

1. ✅ `state_machine.py` - 渐进式披露状态机
2. ✅ `tool_interceptor.py` - 工具拦截器
3. ⚠️ `__init__.py` - 整合导出

### 第二优先级 (应该实现)

4. ⚠️ `loader.py` 修改 - 标准路径
5. ⚠️ `base.py` 修改 - 严格验证
6. ✅ `resource_loader.py` - 资源加载

### 第三优先级 (可选实现)

7. ✅ `sandbox_integrator.py` - 沙箱集成
8. ✅ `path_discovery.py` - 路径发现

---

## 八、总结

本指南提供了 goose-system 技能系统的完整实现方案，对齐了：

1. ✅ Agent Skills 架构设计手册的三级渐进式披露
2. ✅ Agent Skills 运行时验收测试手册的测试用例
3. ✅ goose-rs 项目的实现方式和代码结构

**下一步行动**：
1. 创建 `state_machine.py` 和 `tool_interceptor.py` (已创建)
2. 修改 `__init__.py` 导出新增组件
3. 修改 `loader.py` 添加标准路径
4. 修改 `base.py` 添加严格验证
5. 运行测试验证实现
