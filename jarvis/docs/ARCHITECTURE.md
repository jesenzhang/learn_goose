一套「分布式、事件溯源、可重放的 Agent Runtime
下面我给你的是**生产级、能落地、抗灾、能 debug、能 replay** 的完整设计，不是 PPT 架构。

---

# 一句话定义

> **Agent = 纯状态机 + 事件驱动执行器 + 外部能力适配层**
> **所有副作用都可失败，所有状态都可回放**

---

# 一、总体架构（先给全景）

```
┌─────────────────────────────────────────────┐
│                 Control Plane               │
│  (API / UI / Scheduler / Config / Admin)   │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│               Agent Runtime Core             │
│                                             │
│  ┌───────────┐   ┌─────────────────────┐  │
│  │ Event Bus │◄──►│   Execution Engine  │  │
│  └───────────┘   │ (Async / Concurrent)│  │
│        ▲          └──────────┬──────────┘  │
│        │                     │             │
│  ┌─────────────┐      ┌───────────────┐   │
│  │ State Store │◄────►│ Agent FSM     │   │
│  │ (Snapshot + │      │ (Pure Logic)  │   │
│  │  Event Log) │      └───────────────┘   │
│        ▲                                   │
│        │                                   │
│  ┌──────────────┐   ┌──────────────────┐ │
│  │ Replay Engine│   │ Failure Manager  │ │
│  └──────────────┘   └──────────────────┘ │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│              Capability Plane               │
│                                             │
│  Tools | MCP | Skills | SubAgents | Human  │
│  (全部是“可失败外部系统”)                  │
└─────────────────────────────────────────────┘
```

---

# 二、核心设计哲学（非常重要）

## 1️⃣ Agent 永远不是线程、不是任务、不是 coroutine

**Agent = 状态机（FSM）**

```text
Agent = State + Reducer(Event) -> New State
```

* ❌ Agent 内不直接 await 外部系统
* ❌ 不直接调用 DB / MQ / HTTP
* ✅ 只产生「意图事件」

---

## 2️⃣ 所有执行 = 事件驱动

```
External Trigger
  ↓
Event
  ↓
Reducer
  ↓
New State + Commands
  ↓
Command → Effect → New Event
```

这保证了：

* 可 replay
* 可 debug
* 可 crash 恢复
* 可 time travel

---

## 3️⃣ 所有 IO 都是「Effect」

```python
Effect = 描述我要做什么
Executor = 决定什么时候、是否、如何做
```

---

# 三、模块拆解（逐个讲）

---

## 1️⃣ Event System（整个系统的脊梁）

### Event 类型

```python
class Event:
    event_id: str
    session_id: str
    agent_id: str
    type: str
    payload: dict
    causation_id: str | None
    correlation_id: str
    ts: datetime
```

### 事件分类

| 类型          | 说明                   |
| ----------- | -------------------- |
| InputEvent  | 用户 / API / 定时器       |
| AgentEvent  | Agent 内部状态变化         |
| ToolEvent   | 工具调用结果               |
| ErrorEvent  | 可恢复 / 不可恢复错误         |
| HumanEvent  | 人工介入                 |
| SystemEvent | 调度 / 心跳 / checkpoint |

👉 **所有事情最终都是 Event**

---

## 2️⃣ Event Store（可回放核心）

> **必须是 append-only**

### 存储结构

```
event_log
 ├── session_id
 │    ├── 0001.json
 │    ├── 0002.json
 │    └── ...
```

### 技术选型

* 单机：SQLite + WAL
* 分布式：

  * Kafka / Pulsar（流）
  * Postgres + append table
  * S3 + manifest（低成本）

### 必须支持

* 顺序读取
* 按 session replay
* 幂等写入

---

## 3️⃣ State Store（Snapshot + Event）

```
State(t) = Snapshot(n) + Events(n+1...t)
```

### Snapshot 策略

* 每 N 个事件
* 或重要状态点（human approval 后）

### 好处

* 快速恢复
* 支持 rewind

---

## 4️⃣ Agent FSM（纯逻辑）

```python
class Agent:
    def reduce(self, state, event) -> (new_state, effects):
        ...
```

### 特点

* 纯函数
* 无 IO
* 可测试
* 可 replay

### 支持模式

* Swarm（多个 Agent 订阅同一事件）
* Orchestration（父 Agent 发指令）

---

## 5️⃣ Execution Engine（异步 / 并发）

### 职责

* 执行 Effects
* 不阻塞 Agent
* 控制并发
* 失败重试

```python
class EffectExecutor:
    async def execute(effect) -> Event
```

### 关键点

* 每个 Effect 有 timeout / retry / circuit breaker
* Executor crash 不影响 Agent

---

## 6️⃣ Failure Manager（抗灾核心）

### 故障模型

| 故障             | 处理                             |
| -------------- | ------------------------------ |
| DB down        | 事件写 WAL，延迟提交                   |
| Tool 超时        | retry → fallback → error event |
| Agent crash    | replay                         |
| Executor crash | 重放 effect                      |
| 网络分区           | eventual consistency           |

---

## 7️⃣ Replay Engine（debug 神器）

### 功能

* 从任意 Event replay
* 修改输入重新跑
* 只 dry-run（不执行 effect）

```python
replay(session_id, until_event=N, mode="dry-run")
```

---

## 8️⃣ Workflow / DAG / Recipe

### 本质

> **Workflow = 高级 Event Generator**

```yaml
nodes:
  - id: analyze
    agent: analyzer
  - id: call_tool
    agent: tool_agent
edges:
  - analyze -> call_tool
```

* 每个节点 = Agent
* 边 = Event Routing

---

## 9️⃣ MCP / Skills / SubAgent

### MCP

* MCP Server = Tool Provider
* MCP Client = EffectExecutor Adapter

### Skill

```python
Skill = 封装好的 Agent + Tool 组合
```

### SubAgent

* 拥有独立 session_id
* 父 Agent 只收结果 Event

---

## 🔟 Human-in-the-loop

```text
Agent → RequestApprovalEvent
     → UI
     → HumanDecisionEvent
```

* 人 = 外部系统
* 一样可 replay

---

# 四、并发模型（重点）

### Session 级隔离

* 一个 session = 一条事件流
* 不共享状态

### 并发策略

* 同 session：顺序 reduce
* 不同 session：并行

### Executor 并发池

```text
Agent Logic  (single-thread)
↓
Effect Queue (async, parallel)
```

---

# 五、热更新 & 配置驱动

## Agent 定义

```yaml
agent:
  name: planner
  version: v3
  reducer: planner_v3.reduce
```

* 新 session 用新版本
* 老 session replay 用旧版本

---

# 六、最小可落地技术栈建议

| 模块          | 推荐                    |
| ----------- | --------------------- |
| Runtime     | Python asyncio        |
| Event Store | Postgres / Kafka      |
| Snapshot    | Redis / Postgres      |
| Executor    | asyncio + worker pool |
| Workflow    | 自研 DSL                |
| UI          | 任意（只看 Event）          |

---

# 七、你这个系统 vs LangGraph / AutoGen

| 能力       | 你这个    |
| -------- | ------ |
| 可 replay | ✅      |
| 抗 crash  | ✅      |
| 事件审计     | ✅      |
| 多 Agent  | ✅      |
| 并发       | ✅      |
| 工程化      | **碾压** |

---


> **最小可跑（MVP）+ 生产级可扩展方向明确**
> **事件溯源 / 可回放 / 抗 crash 的 Agent Runtime**

# 一、系统最小闭环（你要先跑起来的）

**最小可跑 = 这 6 个东西**

```
Event        （事实）
EventStore   （真相源）
Agent        （纯 reducer）
Effect       （副作用声明）
Executor     （副作用执行）
Runtime      （调度循环）
```

只要这 6 个跑通，**后面所有高级能力都是“配置和扩展”**。

---

# 二、目录结构（最小但正确）

```text
agent_runtime/
├── core/
│   ├── event.py          # Event 定义
│   ├── effect.py         # Effect 定义
│   ├── agent.py          # Agent / Reducer
│   ├── state.py          # AgentState
│   ├── runtime.py        # Runtime Loop
│   └── session.py        # Session
│
├── store/
│   ├── event_store.py    # EventStore 接口
│   └── memory_store.py  # 最小实现（内存）
│
├── executor/
│   ├── base.py           # EffectExecutor 接口
│   └── mock.py           # 示例 executor
│
├── examples/
│   └── hello_agent.py    # 能跑的 demo
│
└── main.py
```

---

# 三、核心接口定义（这是“系统宪法”）

## 1️⃣ Event（唯一真相）

```python
# core/event.py
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


@dataclass(frozen=True)
class Event:
    id: str
    session_id: str
    agent_id: str
    type: str
    payload: Dict[str, Any]
    causation_id: Optional[str]
    correlation_id: str
    ts: datetime

    @staticmethod
    def new(
        *,
        session_id: str,
        agent_id: str,
        type: str,
        payload: Dict[str, Any],
        causation_id: Optional[str],
        correlation_id: Optional[str] = None,
    ) -> "Event":
        return Event(
            id=str(uuid.uuid4()),
            session_id=session_id,
            agent_id=agent_id,
            type=type,
            payload=payload,
            causation_id=causation_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            ts=datetime.utcnow(),
        )
```

**关键原则**

* Event **不可变**
* 不允许“更新 Event”
* 一切状态都可由 Event 推导

---

## 2️⃣ AgentState（可序列化）

```python
# core/state.py
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AgentState:
    data: Dict[str, Any] = field(default_factory=dict)
    terminated: bool = False
```

---

## 3️⃣ Effect（副作用声明）

```python
# core/effect.py
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Effect:
    type: str
    payload: Dict[str, Any]
    retry: int = 3
    timeout: float = 30.0
```

---

## 4️⃣ Agent（纯 Reducer）

```python
# core/agent.py
from abc import ABC, abstractmethod
from typing import List, Tuple
from .state import AgentState
from .event import Event
from .effect import Effect


class Agent(ABC):
    id: str

    @abstractmethod
    def reduce(
        self,
        state: AgentState,
        event: Event,
    ) -> Tuple[AgentState, List[Effect]]:
        ...
```

**重要约束**

* ❌ 不准 async
* ❌ 不准 IO
* ✅ 纯逻辑

---

## 5️⃣ EventStore（可回放核心）

```python
# store/event_store.py
from abc import ABC, abstractmethod
from typing import Iterable
from core.event import Event


class EventStore(ABC):
    @abstractmethod
    def append(self, event: Event) -> None:
        ...

    @abstractmethod
    def load(self, session_id: str) -> Iterable[Event]:
        ...
```

### 最小实现（内存）

```python
# store/memory_store.py
from collections import defaultdict
from typing import List
from .event_store import EventStore
from core.event import Event


class MemoryEventStore(EventStore):
    def __init__(self):
        self._events: dict[str, List[Event]] = defaultdict(list)

    def append(self, event: Event) -> None:
        self._events[event.session_id].append(event)

    def load(self, session_id: str):
        return list(self._events.get(session_id, []))
```

---

## 6️⃣ EffectExecutor（IO 边界）

```python
# executor/base.py
from abc import ABC, abstractmethod
from core.effect import Effect
from core.event import Event


class EffectExecutor(ABC):
    @abstractmethod
    async def execute(self, effect: Effect, session_id: str, agent_id: str) -> Event:
        ...
```

---

## 7️⃣ Runtime（最小可跑引擎）

```python
# core/runtime.py
import asyncio
from core.agent import Agent
from core.event import Event
from core.state import AgentState
from core.effect import Effect
from store.event_store import EventStore
from executor.base import EffectExecutor


class Runtime:
    def __init__(
        self,
        agent: Agent,
        store: EventStore,
        executor: EffectExecutor,
    ):
        self.agent = agent
        self.store = store
        self.executor = executor

    async def run(self, session_id: str, initial_event: Event):
        self.store.append(initial_event)

        state = AgentState()

        events = self.store.load(session_id)

        for event in events:
            state, effects = self.agent.reduce(state, event)

            if state.terminated:
                break

            for effect in effects:
                result_event = await self.executor.execute(
                    effect,
                    session_id=session_id,
                    agent_id=self.agent.id,
                )
                self.store.append(result_event)
```

> ⚠️ 注意：
> 这是 **最小闭环**，并发 / 调度 / 重试稍后加
> 但 replay 已经天然支持了

---

# 四、一个能跑的完整示例

## 示例 Agent

```python
# examples/hello_agent.py
from core.agent import Agent
from core.state import AgentState
from core.event import Event
from core.effect import Effect


class HelloAgent(Agent):
    id = "hello"

    def reduce(self, state: AgentState, event: Event):
        if event.type == "start":
            return state, [
                Effect(
                    type="print",
                    payload={"text": "Hello, Agent Runtime!"},
                )
            ]

        if event.type == "print.done":
            state.terminated = True
            return state, []

        return state, []
```

## 示例 Executor

```python
# executor/mock.py
from executor.base import EffectExecutor
from core.effect import Effect
from core.event import Event


class MockExecutor(EffectExecutor):
    async def execute(self, effect: Effect, session_id: str, agent_id: str) -> Event:
        if effect.type == "print":
            print(effect.payload["text"])
            return Event.new(
                session_id=session_id,
                agent_id=agent_id,
                type="print.done",
                payload={},
                causation_id=None,
            )
        raise RuntimeError("Unknown effect")
```

## main.py

```python
# main.py
import asyncio
from core.event import Event
from core.runtime import Runtime
from store.memory_store import MemoryEventStore
from executor.mock import MockExecutor
from examples.hello_agent import HelloAgent


async def main():
    store = MemoryEventStore()
    agent = HelloAgent()
    executor = MockExecutor()

    runtime = Runtime(agent, store, executor)

    start = Event.new(
        session_id="s1",
        agent_id=agent.id,
        type="start",
        payload={},
        causation_id=None,
    )

    await runtime.run("s1", start)


if __name__ == "__main__":
    asyncio.run(main())
```

👉 **你现在已经有：**

* Event log
* Agent reducer
* Effect executor
* 可 replay（重新 `run` 即可）

---

# 五、这个骨架如何“自然长大”

| 能力        | 怎么加                             |
| --------- | ------------------------------- |
| 并发        | EffectExecutor → queue + worker |
| Streaming | Effect → chunk Event            |
| Replay    | 从 EventStore 重新跑                |
| Snapshot  | state 持久化                       |
| HITL      | Effect = request_human          |
| MCP       | 新 Executor                      |
| Workflow  | Event Router                    |
| Swarm     | 多 Agent 订阅                      |

**核心接口不用改。**

---


## 下一步

1️⃣ **并发 + 非阻塞 Runtime（Agent 永远不 await）**
2️⃣ **EventStore 的 Postgres / Kafka 版本**
3️⃣ **Replay / Time-travel CLI**
4️⃣ **多 Agent / Swarm / Orchestrator 模式**
5️⃣ **Human-in-the-loop + UI 事件协议**
