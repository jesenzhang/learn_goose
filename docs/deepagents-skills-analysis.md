# DeepAgents 技能系统深度分析文档

## 目录
1. [概述](#概述)
2. [Skills 实现部分](#skills-实现部分)
3. [AGENTS.md 实现部分](#agentsmd-实现部分)
4. [设计模式分析](#设计模式分析)
5. [与 assistant 技能系统对比](#与-assistant-技能系统对比)
6. [优化建议](#优化建议)

---

## 概述

DeepAgents 的技能系统是一个遵循 Anthropic Agent Skills 规范的模块化实现，具有以下特点：

- **渐进式披露**：先显示技能元数据，完整内容按需加载
- **分层源管理**：支持 base -> user -> project -> team skills 优先级
- **后端抽象**：通过 BackendProtocol 支持多种存储方式
- **中间件模式**：通过 AgentMiddleware 实现功能扩展
- **热重载支持**：每次 agent 交互前重新加载技能

---

## Skills 实现部分

### 1.1 Skill 定义方式和结构

**核心文件**: `F:\Workspace\learn_goose\deepagents\libs\deepagents\deepagents\middleware\skills.py`

Skill 的定义完全遵循 **Anthropic Agent Skills 规范**，每个 Skill 是一个目录，包含 `SKILL.md` 文件：

```
/skills/
├── skill-name/           # 目录名必须与 skill name 匹配
│   ├── SKILL.md          # 必需：YAML frontmatter + markdown 指令
│   └── helper.py         # 可选：辅助文件
```

**SKILL.md 文件格式**：

```markdown
---
name: web-research
description: Structured approach to conducting thorough web research
license: MIT
---

# Web Research Skill

## When to Use
- User asks you to research a topic
...
```

### 1.2 SkillMetadata TypedDict 结构

```python
class SkillMetadata(TypedDict):
    name: str                    # Skill 标识符 (max 64 chars)
    description: str             # Skill 描述 (max 1024 chars)
    path: str                    # SKILL.md 文件路径
    license: str | None           # 许可证
    compatibility: str | None      # 环境要求
    metadata: dict[str, str]      # 额外元数据
    allowed_tools: list[str]       # 预批准的工具列表
```

### 1.3 Skill 加载和注册机制

**关键代码** (`skills.py: L284-357`):

```python
def _list_skills(backend: BackendProtocol, source_path: str) -> list[SkillMetadata]:
    """从后端源加载所有技能"""
    base_path = source_path
    skills: list[SkillMetadata] = []
    items = backend.ls_ls_info(base_path)

    # 查找所有包含 SKILL.md 的技能目录
    skill_dirs = []
    for item in items:
        if not item.get("is_dir"):
            continue
        skill_dirs.append(item["path"])

    # 下载每个 SKILL.md 并解析
    for skill_dir_path in skill_dirs:
        skill_dir = PurePosixPath(skill_dir_path)
        skill_md_path = str(skill_dir / "SKILL.md")
        # ... 下载并解析
```

**分层加载机制** (`skills.py: L616-624`):
- 支持多个源，按顺序加载
- 后面的源覆盖前面的同名 skill（last one wins）
- 实现分层：base -> user -> project -> team skills

### 1.4 Tool/Function 注册方式

**文件**: `F:\Workspace\learn_goose\deepagents\libs\deepagents\deepagents\middleware\filesystem.py`

Tools 使用 **LangChain StructuredTool** 模式动态生成：

```python
TOOL_GENERATORS = {
    "ls": _ls_tool_generator,
    "read_file": _read_file_tool_generator,
    "write_file": _write_file_tool_generator,
    "edit_file": _edit_file_tool_generator,
    "glob": _glob_tool_generator,
    "grep": _grep_tool_generator,
    "execute": _execute_tool_generator,
}

def _ls_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 ls 工具"""

    def sync_ls(
        runtime: ToolRuntime[None, FilesystemState],
        path: Annotated[str, "Absolute path to directory to list"],
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(path)
        infos = resolved_backend.ls_info(validated_path)
        # ...

    return StructuredTool.from_function(
        name="ls",
        description=tool_description,
        func=sync_ls,
        coroutine=async_ls,  # 同时支持同步和异步
    )
```

### 1.5 Skill 配置系统

**SkillsMiddleware 类** (`skills.py: L476-694`):

```python
class SkillsMiddleware(AgentMiddleware):
    """加载和暴露 agent skills 到系统提示的中间件"""

    def __init__(self, *, backend: BACKEND_TYPES, sources: list[str]) -> None:
        self._backend = backend          # 后端实例或工厂函数
        self.sources = sources              # 技能源路径列表
        self.system_prompt_template = SKILLS_SYSTEM_PROMPT

    def before_agent(self, state, runtime, config):
        """在 agent 执行前加载技能元数据（同步）"""
        if "skills_metadata" in state:
            return None  # 跳过如果已存在

        backend = self._get_backend(state, runtime, config)
        all_skills: dict[str, SkillMetadata] = {}

        # 按顺序从每个源加载技能
        for source_path in self.sources:
            source_skills = _list_skills(backend, source_path)
            for skill in source_skills:
                all_skills[skill["name"]] = skill  # 后面的覆盖前面的

        return SkillsStateUpdate(skills_metadata=list(all_skills.values()))
```

### 1.6 Skill 生命周期管理

**生命周期钩子**：
1. **初始化** (`__init__`)：配置 backend 和 sources
2. **before_agent/abefore_agent**：每次 agent 交互前重新加载技能（支持热重载）
3. **modify_request**：将技能文档注入到系统提示中
4. **wrap_model_call/awrap_model_call**：包装模型调用，修改请求

---

## AGENTS.md 实现部分

### 2.1 AGENTS.md 文件格式和结构

**核心文件**: `F:\Workspace\learn_goose\deepagents\libs\deepagents\deepagents\middleware\memory.py`

AGENTS.md 是标准的 Markdown 文件，无需特定结构。常见部分包括：
- 项目概览
- 构建/测试命令
- 代码风格指南
- 架构说明

**示例** (`F:\Workspace\learn_goose\deepagents\examples\text-to-sql-agent\AGENTS.md`):

```markdown
# Text-to-SQL Agent Instructions

You are a Deep Agent designed to be helpful, harmless, and honest.

## Your Role
Given a natural about music question, you will:
1. Explore the available database tables
2. Examine relevant table schemas
3. Generate syntactically correct SQL queries
4. Execute the queries and provide clear results to the user

## Database Information
- Database type: SQLite (Chinari database)
...

## Query Guidelines
- Always limit results to 5 rows unless user specifies otherwise
...
```

### 2.2 AGENTS.md 解析机制

**MemoryMiddleware 类** (`memory.py: L155-409`):

```python
class MemoryMiddleware(AgentMiddleware):
    """从 AGENTS.md 文件加载 agent 记忆/上下文的中间件"""

    def __init__(
        self,
        *,
        backend: BACKEND_TYPES,
        sources: list[str],  # AGENTS.md 文件路径列表
    ) -> None:
        self._backend = backend
        self.sources = sources

    async def _load_memory_from_backend(
        self, backend: BackendProtocol, path: str
    ) -> str | None:
        """从后端路径加载记忆内容"""
        results = await backend.adownload_files([path])
        response = results[0]

        if response.error is not None:
            if response.error == "file_not_found":
                return None  # 文件不存在是可接受的
            raise ValueError(f"Failed to download {path}: {response.error}")

        if response.content is not None:
            return response.content.decode("utf-8")
        return None
```

### 2.3 AGENTS.md 中的 Skills 定义方式

**注意**：AGENTS.md 本身不直接定义 Skills，而是作为 agent 的**持久记忆和上下文**。Skills 是通过 `SkillsMiddleware` 单独管理的。

**实际使用示例** (`F:\Workspace\learn_goose\deepagents\examples\text-to-sql-agent\agent.py`):

```python
agent = create_deep_agent(
    model=model,
    memory=["./AGENTS.md"],           # AGENTS.md 提供 agent 身份和通用指令
    skills=["./skills/"],               # skills 提供专门的工作流
    tools=sql_tools,                    # SQL 数据库工具
    backend=FilesystemBackend(root_dir=base_dir)
)
```

### 2.4 AGENTS.md 与实际技能代码的关联

**关联方式**：
1. **AGENTS.md** 通过 `MemoryMiddleware` 加载，内容直接注入到系统提示中
2. **Skills** 通过 `SkillsMiddleware` 加载，采用**渐进式披露**模式：
   - 首先只显示 skill 名称和描述
   - Agent 可以按需读取完整 SKILL.md 内容
   - Skills 可以包含辅助脚本，通过绝对路径访问

**系统提示模板** (`skills.py: L434-473`):

```python
SKILLS_SYSTEM_PROMPT = """

## Skills System

You have access to a skills library that provides specialized capabilities and domain knowledge.

{skills_locations}

**Available Skills:**

{skills_list}

**How to Use Skills (Progressive Disclosure):**

Skills follow a **progressive disclosure** pattern - you see their name and description above, but only read full instructions when needed:

1. **Recognize when a skill applies**: Check if the user's task matches a skill's description
2. **Read the skill's full instructions**: Use the path shown in the skill list above
3. **Follow the skill's instructions**: SKILL.md contains the workflow, best practices, and examples
4. **Access supporting files**: Skills may include helper scripts, configs, or reference docs - use absolute paths
...
"""
```

---

## 设计模式分析

### 3.1 注册表模式 (Registry Pattern)

**文件**: `F:\Workspace\learn_goose\deepagents\libs\deepagents\deepagents\middleware\filesystem.py`

```python
TOOL_GENERATORS = {
    "ls": _ls_tool_generator,
    "read_file": _read_file_tool_generator,
    "write_file": _write_file_tool_generator,
    "edit_file": _edit_file_tool_generator,
    "glob": _glob_tool_generator,
    "grep": _grep_tool_generator,
    "execute": _execute_tool_generator,
}

def _get_filesystem_tools(backend, custom_tool_descriptions=None) -> list[BaseTool]:
    """获取文件系统和执行工具"""
    if custom_tool_descriptions is None:
        custom_tool_descriptions = {}
    tools = []

    for tool_name, tool_generator in TOOL_GENERATORS.items():
        tool = tool_generator(backend, custom_tool_descriptions.get(tool_name))
        tools.append(tool)
    return tools
```

### 3.2 工厂模式 (Factory Pattern)

**后端工厂** (`protocol.py: L457-458`):

```python
BackendFactory: TypeAlias = Callable[[ToolRuntime], BackendProtocol]
BACKEND_TYPES = BackendProtocol | BackendFactory
```

**使用工厂函数支持 StateBackend**：

```python
# 使用工厂函数
backend = lambda rt: StateBackend(rt)

middleware = SkillsMiddleware(backend=backend, sources=[...])

# Resolution
def _get_backend(self, state, runtime, config) -> BackendProtocol:
    if callable(self._backend):
        tool_runtime = ToolRuntime(
            state=state,
            context=runtime.context,
            stream_writer=runtime.stream_writer,
            store=runtime.store,
            config=config,
            tool_call_id=None,
        )
        backend = self._get_backend(tool_runtime)
        return backend
    return self._backend
```

### 3.3 中间件模式 (Middleware Pattern)

**AgentMiddleware 接口** (`skills.py`, `memory.py`, `filesystem.py`):

```python
class SkillsMiddleware(AgentMiddleware):
    state_schema = SkillsState  # 定义状态模式

    def before_agent(self, state, runtime, config):
        """在 agent 执行前运行"""
        # 加载技能元数据

    def modify_request(self, request) -> ModelRequest:
        """修改模型请求"""
        # 注入技能文档到系统提示

    def wrap_model_call(self, request, handler):
        """包装模型调用"""
        modified_request = self.modify_request(request)
        return handler(modified_request)
```

**中间件堆栈** (`graph.py: L180-213`):

```python
# 构建主 agent 中间件堆栈
deepagent_middleware: list[AgentMiddleware] = [
    TodoListMiddleware(),
]
if memory is not None:
    deep:middleware.append(MemoryMiddleware(backend=backend, sources=memory))
if skills is not None:
    deepagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
deepagent_middleware.extend([
    FilesystemMiddleware(backend=backend),
    SubAgentMiddleware(...),
    SummarizationMiddleware(...),
    AnthropicPromptCachingMiddleware(...),
    PatchToolCallsMiddleware(),
])
```

### 3.4 后端协议模式 (Backend Protocol Pattern)

**文件**: `F:\Workspace\learn_goose\deepagents\libs\deepagents\deepagents\backends\protocol.py`

```python
class BackendProtocol(abc.ABC):
    """可插拔存储后端的协议"""

    def ls_info(self, path: str) -> list[FileInfo]:
        """列出目录中的文件，带元数据"""

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """读取文件内容，带行号"""

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入新文件"""

    def edit(self, file_path: str, old_string: str, new_string: str,
             replace_all: bool = False) -> EditResult:
        """编辑文件，执行字符串替换"""

    def grep_raw(self, pattern: str, path: str | None = None,
                glob: str | None = None) -> list[GrepMatch] | str:
        """搜索文件中的文本模式"""

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """查找匹配 glob 模式的文件"""

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量下载文件"""

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量上传文件"""

class SandboxBackendProtocol(BackendProtocol):
    """带隔离运行时的沙盒化后端协议"""

    def execute(self, command: str) -> ExecuteResponse:
        """在进程中执行命令"""

    @property
    def id(self) -> str:
        """沙盒后端实例的唯一标识符"""
```

### 3.5 观察者/事件系统模式

**文件**: `F:\Workspace\learn_goose\deepagents\libs\deepagents\deepagents\middleware\filesystem.py`

中间件通过 **wrap_model_call/wrap_tool_call** 钩子观察和修改请求/响应：

```python
def wrap_model_call(
    self,
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """更新系统提示并基于后端能力过滤工具"""
    # 检查 execute 工具是否存在以及后端是否支持它
    has_execute_tool = any(
        (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
        for tool in request.tools
    )

    backend_supports_execution = False
    if has_execute_tool:
        backend = self._get_backend(request.runtime)
        backend_supports_execution = _supports_execution(backend)

        # 如果 execute 工具存在但后端不支持，将其过滤掉
        if not backend_supports_execution:
            filtered_tools = [
                tool for tool in request.tools
                if (tool.name if hasattr(tool, "name") else tool.get("name")) != "execute"
            ]
            request = request.override(tools=filtered_tools)

    # 动态构建系统提示
    system_prompt = self._build_system_prompt(has_execute_tool and backend_supports_execution)
    new_system_message = append_to_system_message(request.system_message, system_prompt)
    request = request.override(system_message=new_system_message)

    return handler(request)
```

---

## 与 assistant 技能系统对比

### 功能对比表

| 特性 | DeepAgents | Assistant |
|------|-----------|-----------|
| **技能类型** | 纯 Markdown 文档（渐进式披露） | Python 代码 + Markdown |
| **执行方式** | 文档内容作为系统提示 | 直接调用 Python 函数 |
| **配置系统** | 无特定技能配置 | 支持 YAML 多层配置覆盖 |
| **技能类型** | 单一类型 | Global / Contextual 两种类型 |
| **热重载** | 支持（before_agent 钩子） | 支持（reload_skill） |
| **多源支持** | 支持（分层源管理） | 单一目录 |
| **AGENTS.md** | 支持（MemoryMiddleware） | 不支持 |
| **后端抽象** | BackendProtocol | 无 |
| **中间件模式** | 完整中间件系统 | 无 |
| **Claude 兼容** | 完全兼容 | 不直接兼容 |

### 架构对比

**DeepAgents 架构**:
```
DeepAgent
├── Middleware Stack
│   ├── MemoryMiddleware (AGENTS.md)
│   ├── SkillsMiddleware (SKILL.md)
│   ├── FilesystemMiddleware (文件系统工具)
│   └── ...
└── BackendProtocol (存储抽象)
    ├── FilesystemBackend
    ├── StateBackend
    └── CompositeBackend
```

**Assistant 架构**:
```
Assistant
├── Agent
│   ├── SkillLoader
│   ├── AgentGeneration
│   └── Executor
└── Skills
    ├── SkillBase
    └── GenericSkill
```

---

## 优化建议

### 1. 实现 AGENTS.md 支持

**目标**: 支持 AGENTS.md 文件作为 agent 的持久记忆和上下文

**实现方式**:
```python
# 新增: src/assistant/core/memory.py
class AgentMemory:
    """Agent 持久记忆管理器"""

    def __init__(self, memory_paths: List[str]):
        self.memory_paths = memory_paths
        self._memory_content: str = ""

    def load(self) -> str:
        """加载所有 AGENTS.md 内容"""
        content_parts = []
        for path in self.memory_paths:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content_parts.append(f.read())
        self._memory_content = '\n\n'.join(content_parts)
        return self._memory_content

    def get_system_prompt(self) -> str:
        """获取系统提示"""
        return self._memory_content
```

### 2. 实现渐进式披露 (Progressive Disclosure)

**目标**: 类似 DeepAgents，先显示技能元数据，完整内容按需加载

**实现方式**:
```python
# 修改: src/assistant/skills/loader.py
class SkillMetadata(TypedDict):
    name: str
    description: str
    path: str
    full_content: str  # 完整 SKILL.md 内容（可选）

class SkillLoader:
    def get_skills_summary(self) -> str:
        """获取技能摘要（仅名称和描述）"""
        summary = "## Available Skills\n\n"
        for skill_id, skill in self._skills.items():
            summary += f"- **{skill_id}**: {skill.description}\n"
        return summary

    def get_skill_content(self, skill_id: str) -> str:
        """获取技能完整内容"""
        if skill_id not in self._skills:
            return ""
        skill = self._skills[skill_id]
        return skill.get_system_prompt()
```

### 3. 实现后端抽象

**目标**: 支持 BackendProtocol，可扩展不同的存储后端

**实现方式**:
```python
# 新增: src/assistant/core/backend.py
class BackendProtocol(ABC):
    """存储后端协议"""

    @abstractmethod
    def read(self, path: str) -> str:
        """读取文件内容"""
        pass

    @abstractmethod
    def write(self, path: str, content: str) -> None:
        """写入文件"""
        pass

    @abstractmethod
    def list_dir(self, path: str) -> List[str]:
        """列出目录"""
        pass

class FilesystemBackend(BackendProtocol):
    """文件系统后端"""

    def read(self, path: str) -> str:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def write(self, path: str, content: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def list_dir(self, path: str) -> List[str]:
        return [f.name for f in os.scandir(path) if not f.name.startswith('.')]
```

### 4. 实现多源支持

**目标**: 支持从多个目录加载技能，后面的覆盖前面的

**实现方式**:
```python
# 修改: src/assistant/skills/loader.py
class SkillLoader:
    def __init__(
        self,
        skills_dirs: Union[str, List[str]],  # 支持单个或多个目录
        skills_config: Optional[SkillsConfig] = None,
        global_sensitive_tools: Optional[Set[str]] = None,
    ):
        self.skills_dirs = (
            [Path(skills_dirs)]
            if isinstance(skills_dirs, str)
            else [Path(d) for d in skills_dirs]
        )
        # ...

    def load_from_directories(self) -> None:
        """从所有配置的目录加载技能"""
        all_skills: Dict[str, Tuple[SkillBase, Path]] = {}

        # 按顺序加载，后面的覆盖前面的
        for skills_dir in self.skills_dirs:
            for skill_path in skills_dir.iterdir():
                if not skill_path.is_dir() or skill_path.name.startswith(('.', '_')):
                    continue
                skill_id = skill_path.name
                try:
                    skill = self._load_single_skill(skill_id, skill_path)
                    if skill:
                        all_skills[skill_id] = (skill, skill_path)
                except Exception as e:
                    logger.error(f"Error loading skill '{skill_id}': {e}")

        # 注册所有技能
        for skill_id, (skill, _) in all_skills.items():
            self._register_skill_instance(skill)
```

### 5. 实现中间件模式

**目标**: 支持中间件系统，灵活扩展功能

**实现方式**:
```python
# 新增: src/assistant/core/middleware.py
class AgentMiddleware(ABC):
    """Agent 中间件基类"""

    def before_request(self, request: AgentRequest) -> Optional[AgentRequest]:
        """请求前处理"""
        return None

    def after_response(self, response: AgentResponse) -> Optional[AgentResponse]:
        """响应后处理"""
        return None

class MemoryMiddleware(AgentMiddleware):
    """记忆中间件"""

    def __init__(self, memory_paths: List[str]):
        self.memory = AgentMemory(memory_paths)

    def before_request(self, request: AgentRequest) -> Optional[AgentRequest]:
        """注入记忆内容到系统提示"""
        memory_content = self.memory.load()
        if memory_content:
            request.system_message += f"\n\n{memory_content}"
        return request
```

### 6. 完善文档型技能支持

**目标**: 支持 OpenCode 和 DeepAgents 风格的纯文档技能

**实现方式**:
```python
# 修改: src/assistant/skills/loader.py
class SkillLoader:
    def _load_single_skill(self, skill_id: str, path: Path) -> Optional[SkillBase]:
        """加载单个技能，支持代码型和文档型"""
        # ... 现有逻辑 ...

        # 如果没有类也没有函数，但有 SKILL.md，创建文档型技能
        if not skill_instance and not functions:
            meta = self._load_metadata(path)
            skill_md_path = path / "SKILL.md"
            if skill_md_path.exists():
                # 创建文档型技能
                skill_instance = DocumentSkill(
                    name=meta.get("name", skill_id),
                    description=meta.get("description", ""),
                    md_path=str(skill_md_path)
                )
                skill_instance.skill_type = skill_type

        # ...
```

### 7. 工具注册表模式

**目标**: 使用注册表模式管理工具生成器

**实现方式**:
```python
# 新增: src/assistant/skills/registry.py
TOOL_REGISTRY: Dict[str, Callable] = {}

def register_tool(name: str):
    """工具注册装饰器"""
    def decorator(func):
        TOOL_REGISTRY[name] = func
        return func
    return decorator

# 使用
@register_tool("read_file")
def read_file_tool(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()
```

---

## 总结

DeepAgents 的技能系统设计优秀，具有以下核心优势：

1. **渐进式披露**：减少初始提示长度，提高效率
2. **分层源管理**：支持技能复写和优先级
3. **后端抽象**：灵活支持不同存储方式
4. **中间件模式**：高度模块化和可扩展
5. **Anthropic 兼容**：完全兼容 Claude Skills 规范

Assistant 可以借鉴这些设计，实现更强大、更灵活的技能系统。
