# DB 模块重构说明

## 概述

本次重构使 `db` 模块成为一个通用的基础设施模块，不依赖于 `core` 中的特定类型（如 `AgentState`），同时保持类型安全性。

## 主要变更

### 1. manager.py - 本地数据库管理器

**变更前：**
- 依赖 `AgentState` 类型
- 方法签名：`save_state(self, state: AgentState) -> bool`
- 方法签名：`load_state(self, session_id: str) -> Optional[AgentState]`

**变更后：**
- 操作通用的字典数据
- 方法签名：`save_state(self, session_id: str, state: Dict[str, Any]) -> bool`
- 方法签名：`load_state(self, session_id: str) -> Optional[Dict[str, Any]]`
- 新增事件操作：`save_event`, `load_events`, `delete_events`
- 新增健康检查：`health_check`, `get_stats`

### 2. __init__.py - 统一数据库接口

**变更前：**
- 依赖 `core.state.AgentState`
- 本地数据库的事件操作使用 `state._events` 存储
- 类型提示不统一

**变更后：**
- 不依赖 `core` 模块
- 统一使用字典操作
- 添加完整的类型提示
- 接口方法与 `remote_db` 保持一致

### 3. executor.py - 工具执行器

**变更前：**
- 依赖 `DatabaseManager` 具体类

**变更后：**
- 定义 `DatabaseProtocol` 接口
- 使用 `Protocol` 保持类型安全
- 支持任何实现该协议的数据库类

### 4. agent.py - 代理核心

**变更前：**
```python
state = self.db.load_state(session_id) or AgentState(session_id=session_id)
self.db.save_state(state)
```

**变更后：**
```python
state_data = await self.db.load_state(session_id)
state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)
await self.db.save_state(state.session_id, state.model_dump())
```

## 接口设计

### DatabaseProtocol (executor.py)

定义了所有数据库操作的标准接口：

```python
class DatabaseProtocol(Protocol):
    def save_state(self, session_id: str, state: Dict[str, Any]) -> bool: ...
    def load_state(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    def delete_state(self, session_id: str) -> bool: ...
    def list_sessions(self) -> List[Dict[str, Any]]: ...
    def save_event(self, session_id: str, event: Dict[str, Any]) -> bool: ...
    def load_events(self, session_id: str, limit: Optional[int] = None, since: Optional[str] = None) -> List[Dict[str, Any]]: ...
    def add_memory(self, user_id: str, content: str) -> bool: ...
    def get_memories(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]: ...
    def search_memories(self, user_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]: ...
    def delete_memory(self, memory_id: int) -> bool: ...
    def health_check(self) -> bool: ...
    def close(self): ...
```

## 使用示例

### 基本使用

```python
from assistant.db import DatabaseInterface

# 创建数据库接口
db = DatabaseInterface(
    local_db_path="my_assistant.db",
    use_remote=False
)

# 保存状态
state_dict = {
    "session_id": "session123",
    "status": "idle",
    "history": []
}
await db.save_state("session123", state_dict)

# 加载状态
state_data = await db.load_state("session123")
if state_data:
    print(f"Loaded state: {state_data}")

# 保存事件
event = {
    "type": "token",
    "data": "Hello",
    "timestamp": "2024-01-01T00:00:00"
}
await db.save_event("session123", event)
```

### 与 AgentState 配合使用

```python
from assistant.core.state import AgentState
from assistant.db import DatabaseInterface

db = DatabaseInterface()

# 保存 AgentState
state = AgentState(session_id="session123", title="My Chat")
await db.save_state(state.session_id, state.model_dump())

# 加载 AgentState
state_data = await db.load_state("session123")
if state_data:
    state = AgentState(**state_data)
    print(f"State title: {state.title}")
```

### 切换本地/远端数据库

```python
# 使用本地数据库
db_local = DatabaseInterface(local_db_path="local.db", use_remote=False)

# 使用远端数据库
db_remote = DatabaseInterface(
    remote_db_url="http://db-server:8500",
    remote_db_api_key="secret-key",
    use_remote=True
)

# 两个接口用法完全一致
await db_local.save_state("sid1", {"key": "value"})
await db_remote.save_state("sid1", {"key": "value"})
```

## 优势

1. **解耦合** - `db` 模块不再依赖 `core` 模块，成为独立的通用组件
2. **灵活性** - 支持任何类型的状态对象，只需能序列化为字典
3. **一致性** - 本地和远端数据库使用统一的接口
4. **类型安全** - 使用 `Protocol` 保持类型检查
5. **可扩展** - 易于添加新的数据库后端（如 PostgreSQL、MongoDB）

## 迁移指南

如果你有现有代码依赖旧接口，需要进行以下迁移：

### 1. 更新 save_state 调用

**旧代码：**
```python
self.db.save_state(agent_state)
```

**新代码：**
```python
await self.db.save_state(agent_state.session_id, agent_state.model_dump())
```

### 2. 更新 load_state 调用

**旧代码：**
```python
state = self.db.load_state(session_id)
```

**新代码：**
```python
state_data = await self.db.load_state(session_id)
state = AgentState(**state_data) if state_data else None
```

### 3. 更新事件操作

**旧代码：**
```python
# 事件存储在 state._events
state._events.append(event)
self.db.save_state(state)
```

**新代码：**
```python
# 使用专门的事件存储
await self.db.save_event(session_id, event)
```

## 数据库表结构

### 本地 SQLite 数据库

```sql
-- 会话表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,  -- JSON 格式的状态数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 事件表
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event TEXT NOT NULL,  -- JSON 格式的事件数据
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 记忆表
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

## 注意事项

1. **异步操作** - `DatabaseInterface` 的所有方法都是异步的，需要使用 `await`
2. **字典操作** - 所有数据都以字典格式传递
3. **Pydantic 模型** - AgentState 等模型使用 `model_dump()` 和 `**data` 进行转换
4. **错误处理** - 方法返回 `bool` 表示成功/失败，`None` 表示数据不存在

## 未来改进

1. 添加数据库迁移支持
2. 实现批量操作以提高性能
3. 添加数据库连接池管理
4. 支持更多数据库后端
5. 添加查询优化和索引策略
