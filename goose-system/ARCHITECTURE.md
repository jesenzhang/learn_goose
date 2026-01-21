# Goose-System 架构设计

## 核心概念澄清

### Extension vs Tool vs Skill

| 概念 | 层级 | 定义 | 示例 |
|------|------|------|------|
| **Extension** | 系统级插件 | 独立进程/服务，通过 MCP 协议通信 | 文件系统 MCP 服务器、数据库 MCP 服务器 |
| **Tool** | Agent 级工具 | Agent 可调用的功能单元 | `calculate()`, `list_directory()` |
| **Skill** | 能力包 | 包含工具、工作流、提示的组合 | `calculator` skill, `file-manager` skill |

**关系**：
```
Extension (外部 MCP 服务)
    │
    ├── 提供 Tools (工具)
    │       │
    │       └── Tool: calculate() ──────────────┐
    │                                           ├──→ Skill (calculator)
    │       Tool: list_directory() ──────────────┤
    │                                           └──→ Skill (file-manager)
    │
    └── 提供 Resources (资源)
```

### 六个并行管理器 (Agent Level)

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Extension   │  │   Retry     │  │   Tool Inspection   │ │
│  │ Manager     │  │   Manager   │  │       Manager       │ │
│  │ (MCP 插件)  │  │ (重试逻辑)  │  │   (安全/权限检查)   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Prompt    │  │  Subagent   │  │   Permission        │ │
│  │   Manager   │  │   Handler   │  │     Manager         │ │
│  │ (模板管理)  │  │ (子代理)    │  │   (权限确认)        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Extension 系统 (系统级插件)

### 1.1 Extension 类型

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class ExtensionType(str, Enum):
    STDIO = "stdio"           # 子进程通信
    STREAMABLE_HTTP = "streamable_http"  # HTTP 长连接
    BUILTIN = "builtin"       # 内置扩展
    PLATFORM = "platform"     # 平台扩展
    FRONTEND = "frontend"     # 前端工具扩展
    INLINE_PYTHON = "inline_python"  # 内联 Python
```

### 1.2 Extension 配置

```python
class ExtensionConfig(BaseModel):
    """Extension 配置基类"""
    name: str
    type: ExtensionType
    enabled: bool = True

class StdioExtensionConfig(ExtensionConfig):
    """标准输入/输出扩展配置"""
    type: ExtensionType = ExtensionType.STDIO
    command: str
    args: List[str] = Field(default_factory=list)
    envs: Dict[str, str] = Field(default_factory=dict)
    working_dir: Optional[str] = None

class StreamableHttpExtensionConfig(ExtensionConfig):
    """HTTP 流式扩展配置"""
    type: ExtensionType = ExtensionType.STREAMABLE_HTTP
    uri: str
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: float = 30.0

class BuiltinExtensionConfig(ExtensionConfig):
    """内置扩展配置"""
    type: ExtensionType = ExtensionType.BUILTIN
    module: str
    class_name: str

class FrontendExtensionConfig(ExtensionConfig):
    """前端工具扩展配置"""
    type: ExtensionType = ExtensionType.FRONTEND
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    instructions: str = ""
```

### 1.3 Extension 工厂模式

```python
class ExtensionFactory:
    """Extension 创建工厂"""
    
    @staticmethod
    def create(config: ExtensionConfig) -> "Extension":
        """
        根据配置类型创建对应的 Extension
        
        ExtensionConfig::Stdio { cmd, args, ... } → StdioExtension
        ExtensionConfig::StreamableHttp { uri, ... } → HttpExtension
        ExtensionConfig::Builtin { name, ... } → BuiltinExtension
        ExtensionConfig::Platform { name, ... } → PlatformExtension
        """
        if isinstance(config, StdioExtensionConfig):
            return StdioExtension(config)
        elif isinstance(config, StreamableHttpExtensionConfig):
            return HttpExtension(config)
        elif isinstance(config, BuiltinExtensionConfig):
            return BuiltinExtension(config)
        elif isinstance(config, FrontendExtensionConfig):
            return FrontendExtension(config)
        else:
            raise ValueError(f"Unknown extension config type: {type(config)}")
```

---

## 2. MCP 协议集成

### 2.1 MCP 消息类型

```python
from enum import Enum
from pydantic import BaseModel
from typing import Any, Dict, Optional

class MCPMessageType(str, Enum):
    """MCP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"

class MCPMethod(str, Enum):
    """MCP 方法"""
    INITIALIZE = "initialize"
    LIST_TOOLS = "list_tools"
    CALL_TOOL = "call_tool"
    LIST_RESOURCES = "list_resources"
    READ_RESOURCE = "read_resource"
    SUBSCRIBE = "subscribe"
    NOTIFICATIONS = "notifications"

class MCPRequest(BaseModel):
    """MCP 请求"""
    method: MCPMethod
    params: Optional[Dict[str, Any]] = None
    request_id: str

class MCPResponse(BaseModel):
    """MCP 响应"""
    request_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class MCPNotification(BaseModel):
    """MCP 通知"""
    method: str
    params: Optional[Dict[str, Any]] = None
```

### 2.2 MCP Transport

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class MCPTransport(ABC):
    """MCP 传输层抽象"""
    
    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass
    
    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None:
        """发送消息"""
        pass
    
    @abstractmethod
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        """接收消息流"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass

class StdioTransport(MCPTransport):
    """标准输入/输出传输"""
    
    def __init__(self, command: str, args: List[str], envs: Dict[str, str]):
        self.command = command
        self.args = args
        self.envs = envs
        self.process: Optional[subprocess.Process] = None

class HttpTransport(MCPTransport):
    """HTTP 传输"""
    
    def __init__(self, uri: str, headers: Dict[str, str]):
        self.uri = uri
        self.headers = headers
        self.session: Optional[aiohttp.ClientSession] = None
```

### 2.3 MCP Client

```python
class MCPClient:
    """MCP 客户端"""
    
    def __init__(self, name: str, transport: MCPTransport):
        self.name = name
        self.transport = transport
        self.tools: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
    
    async def initialize(self) -> bool:
        """初始化连接"""
        await self.transport.connect()
        # 发送 initialize 请求
        # 接收工具列表和资源列表
        return True
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出可用工具"""
        return self.tools
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        pass
    
    async def close(self) -> None:
        """关闭连接"""
        await self.transport.close()
```

---

## 3. 六个管理器 (Agent Level)

### 3.1 Extension Manager

```python
class ExtensionManager:
    """
    扩展管理器
    
    职责：
    - 插件生命周期管理（加载/卸载）
    - 工具聚合与缓存
    - MCP 协议通信
    - 资源/提示模板管理
    """
    
    def __init__(self):
        self.extensions: Dict[str, "Extension"] = {}
        self.tools_cache: Optional[List["Tool"]] = None
        self.provider: Optional[Any] = None
    
    async def load_extension(self, config: ExtensionConfig) -> None:
        """加载扩展"""
        pass
    
    async def unload_extension(self, name: str) -> None:
        """卸载扩展"""
        pass
    
    async def get_tools(self) -> List["Tool"]:
        """获取所有工具（带缓存）"""
        pass
    
    async def dispatch_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分发工具调用"""
        pass
```

### 3.2 Retry Manager

```python
class RetryManager:
    """
    重试管理器
    
    职责：
    - 工具执行失败后的自动重试
    - 指数退避策略
    - 最大重试次数控制
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """带重试的执行"""
        pass
```

### 3.3 Tool Inspection Manager

```python
class ToolInspectionManager:
    """
    工具检查管理器 (责任链模式)
    
    检查器链：
    1. SecurityInspector - 安全扫描
    2. PermissionInspector - 权限检查
    3. RepetitionInspector - 重复检测
    """
    
    def __init__(self):
        self.inspectors: List["ToolInspector"] = []
    
    def add_inspector(self, inspector: "ToolInspector") -> None:
        """添加检查器"""
        pass
    
    async def inspect(self, request: "ToolRequest") -> "InspectionResult":
        """执行所有检查"""
        pass

class InspectionResult:
    """检查结果"""
    allowed: bool
    reason: str = ""
    action: str = "allow"  # allow, deny, confirm
```

### 3.4 Prompt Manager

```python
class PromptManager:
    """
    提示管理器
    
    职责：
    - 提示模板管理
    - 动态提示构建
    - 上下文注入
    """
    
    def __init__(self):
        self.templates: Dict[str, str] = {}
        self.context_injectors: List["ContextInjector"] = []
    
    def add_template(self, name: str, template: str) -> None:
        """添加模板"""
        pass
    
    async def build_prompt(
        self,
        base_prompt: str,
        context: Dict[str, Any]
    ) -> str:
        """构建完整提示"""
        pass
```

### 3.5 Subagent Handler

```python
class SubagentHandler:
    """
    子代理处理器
    
    职责：
    - 子 Agent 创建和隔离
    - 任务配置和执行
    - 结果收集
    """
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
    
    async def execute_subagent(
        self,
        task_config: "SubagentConfig"
    ) -> "SubagentResult":
        """执行子代理"""
        pass
    
    def create_isolated_agent(self, config: "SubagentConfig") -> "Agent":
        """创建隔离的 Agent 实例"""
        pass
```

### 3.6 Permission Manager

```python
class PermissionManager:
    """
    权限管理器
    
    职责：
    - 权限策略存储
    - 权限级别检查
    - 用户确认流程
    """
    
    class PermissionLevel(str, Enum):
        ALLOW = "allow"
        ONCE = "once"
        DENY = "deny"
    
    def __init__(self):
        self.policies: Dict[str, PermissionLevel] = {}
        self.pending_confirmations: Dict[str, asyncio.Future] = {}
    
    async def check_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> PermissionLevel:
        """检查权限"""
        pass
    
    async def request_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> bool:
        """请求用户确认"""
        pass
```

---

## 4. Agent 结构

```python
class Agent:
    """Agent 核心类"""
    
    def __init__(self, config: "AgentConfig"):
        self.config = config
        
        # 六个并行管理器
        self.extension_manager = ExtensionManager()
        self.retry_manager = RetryManager()
        self.tool_inspection_manager = ToolInspectionManager()
        self.prompt_manager = PromptManager()
        self.subagent_handler = SubagentHandler(self)
        self.permission_manager = PermissionManager()
        
        # 其他组件
        self.provider: Provider
        self.conversation: Conversation
```

---

## 5. 目录结构

```
goose-system/src/goose/
├── agent/                    # Agent 核心
│   ├── base.py              # Agent 类定义
│   ├── reply.py             # 回复流程
│   ├── state.py             # Agent 状态
│   └── event.py             # 事件系统
│
├── extension/               # Extension 系统 (插件)
│   ├── __init__.py
│   ├── config.py            # Extension 配置
│   ├── factory.py           # Extension 工厂
│   ├── base.py              # Extension 基类
│   ├── stdio.py             # Stdio Extension
│   ├── http.py              # HTTP Extension
│   ├── builtin.py           # Builtin Extension
│   ├── frontend.py          # Frontend Extension
│   └── manager.py           # Extension Manager
│
├── mcp/                      # MCP 协议实现
│   ├── __init__.py
│   ├── transport.py         # 传输层抽象
│   ├── client.py            # MCP Client
│   ├── message.py           # 消息类型
│   └── stdio_transport.py   # Stdio 传输
│   └── http_transport.py    # HTTP 传输
│
├── managers/                 # 六个管理器 (Agent Level)
│   ├── __init__.py
│   ├── retry_manager.py     # 重试管理器
│   ├── inspection_manager.py # 工具检查管理器
│   ├── prompt_manager.py    # 提示管理器
│   ├── subagent_handler.py  # 子代理处理器
│   └── permission_manager.py # 权限管理器
│
├── tools/                    # 工具系统
│   ├── base.py              # Tool 基类
│   ├── executor.py          # 工具执行器
│   └── inspection.py        # 工具检查器
│
├── skills/                   # Skill 系统
│   ├── base.py
│   ├── loader.py
│   ├── impl_loader.py
│   └── registry.py
│
├── providers/                # Provider 系统
│   ├── base.py
│   ├── factory.py
│   └── openai.py
│
├── conversation/             # 对话系统
│   ├── message.py
│   └── __init__.py
│
└── persistence/              # 持久化
    ├── manager.py
    └── ...
```

---

## 6. 总结

### Extension 定义

**Extension = 系统级插件**
- 独立进程/服务，通过 MCP 协议通信
- 可以提供 Tools 和 Resources
- 支持多种连接方式（Stdio、HTTP、内置等）
- 与 Agent 工具的聚合层

### 与 Tool/Skill 的关系

```
Extension (MCP Server)
    ↓ provides
Tools (Python Functions)
    ↓ grouped into
Skills (能力包)
```

### 六个管理器 (Agent 级别)

1. **Extension Manager** - 插件生命周期管理
2. **Retry Manager** - 自动重试逻辑
3. **Tool Inspection Manager** - 安全/权限检查链
4. **Prompt Manager** - 模板管理
5. **Subagent Handler** - 子代理执行
6. **Permission Manager** - 权限确认
