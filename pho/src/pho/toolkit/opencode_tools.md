# Pho 工具系统整合方案（完整版）

## 概述

将 opencode-tool 的 17 个内置工具直接集成到 toolkit 系统，无适配器层，使用配置类型管理执行上下文。

---

## 一、核心架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Unified Toolkit System               │
│                                                       │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────┐
│         ToolRegistry                 │
│         ToolExecutor (Enhanced)    │
│                                       │
└──────────────────────────────────────────────────────┘
           ↓           ↓
┌────────────────────────────────────────────────────┴
│  Builtin Tools (17)            │   Execution Context            │
│  - Bash, Read, Write...         │  - session_id, user_id, variables │
│                                  │  - services (llm, db, ...)   │
└────────────────────────────────────────────────────┘
```

---

## 二、模块结构

### 2.1 执行上下文（新建）

**文件**: `pho/src/pho/core/execution_context.py`

```python
"""
统一执行上下文

使用配置类型管理，支持所有执行场景。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypeVar, Generic, Callable, Union
from enum import Enum


class ExecutionMode(str, Enum):
    """执行模式"""
    WORKFLOW = "workflow"      # DAG 工作流执行
    AGENT = "agent"          # Agent 执行
    TOOL = "tool"           # 直接工具调用


class ExecutionPhase(str, Enum):
    """执行阶段"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    SUSPENDED = "suspended"


@dataclass
class ExecutionState:
    """可序列化的执行状态"""
    phase: ExecutionPhase = ExecutionPhase.IDLE
    variables: Dict[str, Any] = field(default_factory=dict)
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    iteration_count: int = 0
    error_count: int = 0


@dataclass
class RuntimeServices:
    """运行时服务容器（不可序列化）"""
    llm: Optional[Any] = None
    embedding: Optional[Any] = None
    reranker: Optional[Any] = None
    database: Optional[Any] = None
    sandbox: Optional[Any] = None
    executor: Optional[Any] = None
    streamer: Optional[Any] = None
    hooks: Optional[Any] = None


class ExecutionContextConfig:
    """执行上下文配置"""

    execution_id: str
    session_id: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    parent_execution_id: Optional[str] = None

    # 执行控制
    mode: ExecutionMode = ExecutionMode.WORKFLOW
    is_suspended: bool = False
    is_readonly: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "parent_execution_id": self.parent_execution_id,
            "mode": self.mode,
            "is_suspended": self.is_suspended,
            "is_readonly": self.is_readonly,
        }


class ExecutionContext:
    """
    统一执行上下文

    使用配置类型管理，支持：
    - 工作流执行（WorkflowContext）
    - Agent 执行
    - 直接工具调用
    - 嵌套上下文支持
    """

    def __init__(self, config: Optional[ExecutionContextConfig] = None):
        if config:
            self._config = config
        else:
            self._config = ExecutionContextConfig(
                execution_id=f"exec_{id(self)}",
                session_id=f"session_{id(self)}",
            )

        self._state = ExecutionState()
        self._services = RuntimeServices()

    # === 核心标识 ===
    @property
    def execution_id(self) -> str:
        return self._config.execution_id

    @property
    def session_id(self) -> str:
        return self._config.session_id

    @property
    def user_id(self) -> Optional[str]:
        return self._config.user_id

    @property
    def request_id(self) -> Optional[str]:
        return self._config.request_id

    @property
    def parent_execution_id(self) -> Optional[str]:
        return self._config.parent_execution_id

    @property
    def mode(self) -> ExecutionMode:
        return self._config.mode

    @property
    def is_suspended(self) -> bool:
        return self._config.is_suspended

    @property
    def is_readonly(self) -> bool:
        return self._config.is_readonly

    # === 状态管理 ===
    @property
    def state(self) -> ExecutionState:
        return self._state

    @property
    def phase(self) -> ExecutionPhase:
        return self._state.phase

    def set_phase(self, phase: ExecutionPhase) -> None:
        self._state.phase = phase

    @property
    def variables(self) -> Dict[str, Any]:
        return self._state.variables

    @property
    def node_outputs(self) -> Dict[str, Any]:
        return self._state.node_outputs

    def set_variable(self, key: str, value: Any) -> None:
        self._state.variables[key] = value

    def set_node_output(self, node_id: str, output: Any) -> None:
        self._state.node_outputs[node_id] = output

    @property
    def iteration_count(self) -> int:
        return self._state.iteration_count

    @property
    def error_count(self) -> int:
        return self._state.error_count

    def increment_iteration(self) -> None:
        self._state.iteration_count += 1

    def increment_error(self) -> None:
        self._state.error_count += 1

    # === 服务访问 ===
    @property
    def services(self) -> RuntimeServices:
        return self._services

    # 类型安全的快捷访问
    @property
    def llm(self) -> Any:
        if self._services.llm is None:
            raise RuntimeError("LLM service not configured")
        return self._services.llm

    @property
    def embedding(self) -> Any:
        if self._services.embedding is None:
            raise RuntimeError("Embedding service not configured")
        return self._services.embedding

    @property
    def reranker(self) -> Any:
        if self._services.reranker is None:
            raise RuntimeError("Reranker service not configured")
        return self._services.reranker

    @property
    def database(self) -> Any:
        return self._services.database

    @property
    def sandbox(self) -> Any:
        return self._services.sandbox

    @property
    def executor(self) -> Any:
        return self._services.executor

    @property
    def streamer(self) -> Any:
        return self._services.streamer

    @property
    def hooks(self) -> Any:
        return self._services.hooks

    # 服务设置方法（运行时）
    def set_llm(self, llm: Any) -> None:
        self._services.llm = llm

    def set_embedding(self, embedding: Any) -> None:
        self._services.embedding = embedding

    def set_reranker(self, reranker: Any) -> None:
        self._services.reranker = reranker

    def set_database(self, db: Any) -> None:
        self._services.database = db

    def set_sandbox(self, sandbox: Any) -> None:
        self._services.sandbox = sandbox

    def set_executor(self, executor: Any) -> None:
        self._services.executor = executor

    def set_streamer(self, streamer: Any) -> None:
        self._services.streamer = streamer

    def set_hooks(self, hooks: Any) -> None:
        self._services.hooks = hooks

    # === 控制位 ===
    @property
    def is_suspended(self) -> bool:
        return self._config.is_suspended

    def suspend(self) -> None:
        self._config.is_suspended = True

    def resume(self) -> None:
        self._config.is_suspended = False

    @property
    def is_readonly(self) -> bool:
        return self._config.is_readonly

    def set_readonly(self, value: bool = None:
        self._config.is_readonly = value

    # === 嵌套上下文 ===
    @classmethod
    def from_config(cls, config: ExecutionContextConfig) -> "ExecutionContext":
        """从配置创建上下文"""
        return cls(config=config)

    @classmethod
    def child_context(cls, parent: "ExecutionContext", **overrides) -> "ExecutionContext":
        """创建子上下文"""
        child_config = ExecutionContextConfig(
            execution_id=f"exec_{id(parent)}_{id(cls)}",
            session_id=parent.session_id,
            user_id=parent.user_id,
            request_id=parent.request_id,
            parent_execution_id=parent.execution_id,
            mode=parent.mode,
        )

        ctx = cls(config=child_config)

        # 继承状态
        for key in ["variables", "node_outputs"]:
            parent_value = getattr(parent._state, key)
            if parent_value:
                setattr(ctx._state, key, parent_value.copy())

        # 继承服务
        for service_name in ["llm", "embedding", "reranker", "database", "sandbox", "executor", "streamer", "hooks"]:
            service_value = getattr(parent._services, service_name)
            if service_value is not None:
                setattr(ctx._services, service_name, service_value)

        return ctx

    def clone(self) -> "ExecutionContext":
        """克隆当前上下文"""
        # 深度克隆状态
        cloned_state = ExecutionState(
            phase=self._state.phase,
            variables=self._state.variables.copy(),
            node_outputs=self._state.node_outputs.copy(),
            iteration_count=self._state.iteration_count,
            error_count=self._state.error_count,
        )

        # 深度克隆服务（服务通常是共享的，不需要深拷贝）
        return self.__class__(config=self._config)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "config": self._config.to_dict(),
            "state": {
                "phase": self._state.phase.value,
                "variables": self._state.variables,
                "node_outputs": self._state.node_outputs,
                "iteration_count": self._state.iteration_count,
                "error_count": self._state.error_count,
            },
            "services": {
                "llm": "configured" if self._services.llm else "not_configured",
                "embedding": "configured" if self._services.embedding else "not_configured",
                "reranker": "configured" if self._services.reranker else "not_configured",
                "database": "configured" if self._services.database else "not_configured",
                "sandbox": "configured" if self._services.sandbox else "not_configured",
                "executor": "configured" if self._services.executor else "not_configured",
                "streamer": "configured" if self._services.streamer else "not_configured",
                "hooks": "configured" if self._services.hooks else "not_configured",
            }
        }
```

---

### 2.2 Toolkit 注册系统（保持现有）

**文件**: `pho/src/pho/toolkit/registry.py`（保持不变）

已有功能：
- `ToolType`: DECORATOR, SKILL, MCP, BUILTIN
- `ToolMetadata`: name, description, function, tool_type, category, enabled, source, schema
- `ToolRegistry`: register, register_decorator, query methods, execute, OpenAI schema
- `get_global_registry()`: 全局单例
- `register_tool(name, description, category)`: 装饰器

---

### 2.3 Tool 执行器增强

**文件**: `pho/src/pho/toolkit/executor.py`

**修改内容**：

```python
# 新增状态类型
class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CACHED = "cached"

# 修改 execute 方法签名
async def execute(
    self,
    tool_name: str,
    tool_args: Dict[str, Any],
    context: Optional[ExecutionContext] = None  # 使用新的执行上下文
) -> ExecutionResult:
    """执行工具（增强版）"""
    ...

# 保留原有功能：
- Inspector chain
- 缓存
- 重试
- 批量执行
```

---

### 2.4 Opencode-Tool 集成

**文件**: `pho/src/pho/toolkit/opencode_tools.py`

```python
"""
集成 opencode-tool 的 17 个内置工具到 toolkit 系统。

直接修改工具类以符合 toolkit 接口，无需适配器。
"""

from typing import Dict, Any, Optional

from .registry import ToolRegistry, ToolMetadata, ToolType
from .executor import ExecutionResult, ExecutionStatus


def register_opencode_tools(registry: ToolRegistry) -> int:
    """
    注册所有 opencode-tool 内置工具到 toolkit registry

    直接修改工具类以符合 toolkit 接口：
    1. 设置 tool_type=ToolType.BUILTIN
    2. 设置 category="opencode"
    3. 调整 execute 方法返回类型
    """
    from ..tools import builtin as opencode_builtin

    count = 0
    for tool_class_name in opencode_builtin.get_builtin_tool_names():
        tool_class = opencode_builtin.get_tool_class(tool_class_name)
        if not tool_class:
            continue

        # 设置工具类型
        tool_class.tool_type = ToolType.BUILTIN
        tool_class.category = "opencode"

        # 包装原始 execute 方法
        if not hasattr(tool_class, "_original_execute"):
            tool_class._original_execute = tool_class.execute

        # 替换 execute 方法以返回 ExecutionResult
        async def _toolkit_execute(self, **kwargs) -> ExecutionResult:
            """
            Toolkit-compatible execute method

            执行原始工具并转换结果类型
            """
            try:
                # 调用原始 execute（已带验证）
                result = await tool_class._original_execute(kwargs)

                # 转换 ToolResult 到 ExecutionResult
                if hasattr(result, "state"):
                    # opencode-tool returns ToolState enum
                    if result.state.value == "error":
                        return ExecutionResult(
                            status=ExecutionStatus.FAILED,
                            tool_name=tool_class.name,
                            error=result.error
                        )
                    elif result.state.value == "completed":
                        return ExecutionResult(
                            status=ExecutionStatus.COMPLETED,
                            tool_name=tool_class.name,
                            result=result.content,
                        )
                    # 如果是普通返回
                    elif hasattr(result, "error"):
                        return ExecutionResult(
                            status=ExecutionStatus.FAILED,
                            tool_name=tool_class.name,
                            error=result.error
                        )
                    else:
                        return ExecutionResult(
                            status=ExecutionStatus.COMPLETED,
                            tool_name=tool_class.name,
                            result=str(result),
                        )

            except Exception as e:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    tool_name=tool_class.name,
                    error=str(e),
                )

        # 设置新 execute 方法
        tool_class.execute = _toolkit_execute

        # 注册到 toolkit
        registry.register(
            name=tool_class.name,
            func=tool_class.execute,
            description=tool_class.description,
            tool_type=ToolType.BUILTIN,
            category="opencode"
        )
        count += 1

    return count


def get_tool_statistics(registry: ToolRegistry) -> Dict[str, Any]:
    """获取工具统计"""
    from ..tools import builtin as opencode_builtin

    return {
        "total": len(registry),
        "opencode_builtin": len(opencode_builtin.get_builtin_tool_names()),
        "by_category": {
            "opencode": len(opencode_builtin.get_builtin_tool_names())
        }
    }
```

---

## 三、文件修改清单

### 3.1 新建文件

```
pho/src/pho/core/
├── execution_context.py    # NEW: 统一执行上下文
```

### 3.2 修改文件

```
pho/src/pho/toolkit/
├── opencode_tools.py      # NEW: opencode-tool 集成
```

pho/src/pho/toolkit/executor.py
├── 修改 execute 方法签名和状态类型
```

---

## 四、初始化流程

### 4.1 系统启动

```python
from pho.core.execution_context import ExecutionContext
from pho.toolkit import get_global_registry, register_opencode_tools
from pho.skills import SkillLoader  # 如果需要加载技能

# 获取 toolkit 注册表
registry = get_global_registry()

# 注册所有 opencode 内置工具
register_opencode_tools(registry)

# 如果有技能系统，可以也注册技能工具
# skill_loader = SkillLoader()
# skill_loader.load_from_directory()
# for skill in skill_loader.get_available_skills_list():
#     for tool in skill.get_tools():
#         registry.register(...)
```

### 4.2 使用示例

```python
# 创建执行上下文
ctx = ExecutionContext.from_config(
    execution_id="exec_001",
    session_id="session_001",
    user_id="user_123",
)

# 注入服务
ctx.set_llm(llm)
ctx.set_database(db)
ctx.set_sandbox(sandbox)

# 执行工具
from pho.toolkit import get_global_registry

registry = get_global_registry()
result = await registry.execute(
    tool_name="bash",
    ctx=ctx,
    command="ls -la",
)
```

---

## 五、关键优势

1. **简化的集成**：无适配器层，直接修改工具类
2. **统一的执行上下文**：支持工 作流、Agent、工具调用
3. **配置类型管理**：清晰的状态和配置分离
4. **嵌套支持**：通过 parent_execution_id 实现嵌套
5. **控制位**：suspend、readonly 等标志
6. **类型安全**：强类型提示，防止运行时错误

---

## 六、向后兼容

**与现有 WorkflowContext 兼容**：

ExecutionContext 可以作为 WorkflowContext 的替代或补充：
- WorkflowContext 有的属性在 ExecutionContext 中都有对应实现
- WorkflowContext 的 node set_node_output() 对应 set_node_output()
- WorkflowContext 的 variables 对应 variables

**迁移建议**：

1. 对于现有使用 WorkflowContext 的代码，可以保持不变
2. 新代码使用 ExecutionContext 以获得更好的类型安全和功能
3. 或者创建一个 WorkflowContextAdapter 来桥接两个系统
