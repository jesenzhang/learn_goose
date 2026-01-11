# Pho Multi-Style Agent Architecture

## 设计目标

创建一个统一的 Agent 框架，支持多种 Agent 架构模式，用户可以根据场景选择最适合的风格。

## Agent 风格对比

### 1. BaseAgent - 最小化 Agent

**灵感来源**: 基础 LLM + 工具调用模式

**特点**:
- 最简单的实现
- 单轮 LLM 调用
- 同步工具执行
- 无状态管理
- 适合: 简单任务、快速原型

**架构**:
```
User Input → LLM → Tool Execution → Response
```

### 2. StreamingAgent - 流式事件驱动 Agent

**灵感来源**: goose-rs

**特点**:
- 异步流式输出
- 事件总线架构
- 工具检查器链 (Security/Permission/Repetition)
- MCP 扩展支持
- 并发工具执行
- 适合: 生产环境、需要实时反馈

**架构**:
```
User Input → Event Loop → LLM Stream → Inspector Chain → Tool Execution → Events → Client
```

**关键组件**:
- `EventBus`: 事件分发
- `ToolInspectorChain`: 工具调用前检查
- `ExtensionManager`: MCP 扩展管理
- `StreamingExecutor`: 并发工具执行

### 3. ReactAgent - 推理-行动循环 Agent

**灵感来源**: Claude Code, ReAct 模式

**特点**:
- 显式思考过程 (Thought)
- 清晰的行动步骤 (Action)
- 观察结果反馈 (Observation)
- 多轮自主决策
- 适合: 复杂推理任务、需要透明决策过程

**架构**:
```
while not done:
    Thought = LLM("What should I do next?")
    if Thought.should_use_tool:
        Observation = execute_tool(Thought.tool)
        add_to_history(Thought, Observation)
    else:
        return Thought.answer
```

### 4. ThreePhaseAgent - 三阶段 Agent

**灵感来源**: skill_micro_agent

**特点**:
- Phase 1: 意图识别
- Phase 2: LLM 生成循环
- Phase 3: 工具执行 (依赖注入)
- 热重载支持 (Generation 模式)
- 技能系统 (SKILL.md)
- 适合: 需要意图路由、技能编排的场景

**架构**:
```
User Input → Intent Recognizer → [Direct Execution OR LLM Loop → Tools]
```

**关键组件**:
- `IntentRecognizer`: 意图识别
- `SkillLoader`: 技能加载
- `GenerationManager`: 配置热重载
- `ToolExecutor`: 依赖注入执行器

### 5. WorkflowAgent - 工作流驱动 Agent

**灵感来源**: goose-py

**特点**:
- DAG 工作流编排
- 组件系统
- 条件分支
- 子工作流支持
- 适合: 复杂业务流程、需要可视化的场景

**架构**:
```
Workflow Definition → Graph → Scheduler → Component Execution → Results
```

## 统一架构

### 核心抽象

```python
# pho/agent/core.py

from enum import Enum
from abc import ABC, abstractmethod

class ExecutionMode(str, Enum):
    """执行模式"""
    REACT = "react"                    # Thought → Action → Observation
    STREAMING = "streaming"            # 事件流驱动
    THREE_PHASE = "three_phase"        # Intent → LLM → Tools
    WORKFLOW = "workflow"              # DAG 工作流

class AgentStyle(str, Enum):
    """Agent 风格"""
    MINIMAL = "minimal"                # BaseAgent
    REACTIVE = "reactive"              # StreamingAgent
    REASONING = "reasoning"            # ReactAgent
    SKILL_BASED = "skill_based"        # ThreePhaseAgent
    ORCHESTRATED = "orchestrated"      # WorkflowAgent

class AgentEngine(ABC):
    """执行引擎基类"""
    
    @abstractmethod
    async def execute(self, input: str, context: Context) -> AgentResponse:
        """执行 Agent 任务"""
        pass
    
    @abstractmethod
    def get_mode(self) -> ExecutionMode:
        """返回执行模式"""
        pass
```

### PhoAgent 统一接口

```python
# pho/agent/facade.py

class PhoAgent:
    """
    统一 Agent 门面，支持多种风格
    
    用法:
        # 使用默认风格 (Streaming)
        agent = PhoAgent()
        
        # 指定风格
        agent = PhoAgent(style=AgentStyle.REASONING)
        
        # 运行
        response = await agent.run("Hello, world!")
    """
    
    def __init__(
        self,
        style: AgentStyle = AgentStyle.REACTIVE,
        config: AgentConfig = None,
        llm: BaseLLM = None,
        tools: ToolRegistry = None
    ):
        self.style = style
        self.config = config or AgentConfig()
        self.engine = self._create_engine(style)
    
    def _create_engine(self, style: AgentStyle) -> AgentEngine:
        """根据风格创建对应的执行引擎"""
        if style == AgentStyle.MINIMAL:
            return BaseAgentEngine(self.config)
        elif style == AgentStyle.REACTIVE:
            return StreamingAgentEngine(self.config)
        elif style == AgentStyle.REASONING:
            return ReactAgentEngine(self.config)
        elif style == AgentStyle.SKILL_BASED:
            return ThreePhaseAgentEngine(self.config)
        elif style == AgentStyle.ORCHESTRATED:
            return WorkflowAgentEngine(self.config)
        else:
            raise ValueError(f"Unknown style: {style}")
    
    async def run(self, input: str, **kwargs) -> AgentResponse:
        """运行 Agent"""
        context = Context(**kwargs)
        return await self.engine.execute(input, context)
```

### 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                      │
│  CLI, FastAPI, Streamlit, Jupyter, etc.                 │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   PhoAgent Facade                        │
│  Unified interface with style selection                 │
└─────────────────────────────────────────────────────────┘
                           ↓
┌──────────────┬──────────────┬──────────────┬──────────┐
│  ReactEngine │ StreamingEng │ ThreePhaseEng │ Workflow │
│  (Reasoning) │  (Reactive)  │  (SkillBased) │(Orchestr)│
└──────────────┴──────────────┴──────────────┴──────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                     Core Services Layer                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Provider │ │   Tool   │ │  State   │ │  Event   │  │
│  │ Factory  │ │ Registry │ │ Manager  │ │   Bus    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │InspChain │ │Extension │ │   Skill  │ │  Intent  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                    │
│  Persistence, Config, Logging, Metrics                  │
└─────────────────────────────────────────────────────────┘
```

## 使用示例

### 示例 1: 最小化 Agent

```python
from pho import PhoAgent, AgentStyle

# 创建最简单的 Agent
agent = PhoAgent(style=AgentStyle.MINIMAL)

response = await agent.run("What's the weather today?")
print(response.text)
```

### 示例 2: 流式 Agent (生产级)

```python
from pho import PhoAgent, AgentStyle

# 创建流式 Agent，带事件监听
agent = PhoAgent(style=AgentStyle.REACTIVE)

# 监听事件
@agent.on_event("*")
async def handle_all_events(event):
    print(f"Event: {event.type} - {event.data}")

# 流式运行
async for chunk in agent.run_stream("Analyze this data")):
    print(chunk.text, end="")
```

### 示例 3: 推理 Agent (Claude Code 风格)

```python
from pho import PhoAgent, AgentStyle

# 创建显式推理的 Agent
agent = PhoAgent(style=AgentStyle.REASONING)

response = await agent.run("Solve this step by step: ...")

# 查看推理过程
for thought in response.thoughts:
    print(f"Thought: {thought}")
    print(f"Action: {thought.action}")
    print(f"Observation: {thought.observation}")
    print("---")
```

### 示例 4: 技能 Agent

```python
from pho import PhoAgent, AgentStyle

# 创建基于技能的 Agent
agent = PhoAgent(style=AgentStyle.SKILL_BASED)

response = await agent.run("Search for Python tutorials")

# 自动激活 search 技能
# 使用意图识别路由到正确的技能
```

### 示例 5: 工作流 Agent

```python
from pho import PhoAgent, AgentStyle

# 创建工作流驱动的 Agent
agent = PhoAgent(style=AgentStyle.ORCHESTRATED)

response = await agent.run_workflow(
    workflow_id="data_analysis",
    inputs={"dataset": "sales.csv"}
)
```

## 文件结构

```
pho/src/pho/agent/
├── __init__.py           # 导出所有 Agent 类
├── core.py              # 核心抽象 (ExecutionMode, AgentStyle, AgentEngine)
├── facade.py            # PhoAgent 统一接口
│
├── base.py              # BaseAgent 实现
├── streaming.py         # StreamingAgent 实现 (Goose-rs 风格)
├── react.py             # ReactAgent 实现 (Claude Code 风格)
├── three_phase.py       # ThreePhaseAgent 实现 (Skill Micro Agent 风格)
├── workflow.py          # WorkflowAgent 实现 (Goose-py 风格)
│
├── engines/             # 执行引擎
│   ├── __init__.py
│   ├── base.py         # AgentEngine 基类
│   ├── react_engine.py
│   ├── streaming_engine.py
│   ├── three_phase_engine.py
│   └── workflow_engine.py
│
├── inspectors/          # 工具检查器链 (Goose-rs 风格)
│   ├── __init__.py
│   ├── base.py         # ToolInspector 接口
│   ├── security.py     # 安全检查
│   ├── permission.py   # 权限检查
│   └── repetition.py   # 重复检测
│
├── state.py             # 状态管理 (共享)
├── executor.py          # 工具执行器 (共享)
├── generation.py        # 热重载支持
└── events.py            # 事件定义
```

## 下一步

1. 实现核心抽象 (`agent/core.py`)
2. 实现 BaseAgent (`agent/base.py`)
3. 实现 StreamingAgent (`agent/streaming.py`)
4. 实现 ReactAgent (`agent/react.py`)
5. 实现 ThreePhaseAgent (从 skill_micro_agent 迁移)
6. 实现 PhoAgent Facade (`agent/facade.py`)
7. 编写测试和文档
