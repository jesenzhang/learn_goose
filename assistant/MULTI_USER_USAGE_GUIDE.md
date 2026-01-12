# 多用户功能使用指南

## 回答你的问题

### ❌ 误解：原有代码**不会**废弃

**事实**：
1. ✅ 所有原有接口保持不变
2. ✅ 原有代码可以继续使用
3. ✅ 新接口是**额外功能**，不是替换
4. ✅ 可以逐步迁移，不需要一次性重写

---

## 向后兼容性设计

### 1. 原有接口完全保留

```python
# 这些接口继续工作，不会废弃
await db.save_state(session_id, state)
await db.load_state(session_id)
await db.list_sessions()
await db.delete_state(session_id)
```

### 2. 新接口是**扩展**，不是**替换**

```python
# 新接口 - 额外的多用户功能
await db.save_state_for_user(user_id, session_id, state)
await db.load_state_for_user(user_id, session_id)
await db.list_sessions_for_user(user_id)
await db.delete_user_sessions(user_id)
await db.get_user_stats(user_id)
```

### 3. 自动检测 user_id

```python
# 如果 state 中包含 user_id，会自动使用多用户逻辑
state = {
    "session_id": "session123",
    "user_id": "user1",  # 有 user_id 就自动支持多用户
    "status": "idle"
}
await db.save_state(state["session_id"], state)
# 内部会自动调用 save_state_for_user
```

---

## 使用方式对比

### 场景 1：单用户应用（原有方式）

**适用**：个人助手、单用户系统

```python
from assistant.db import get_db
from assistant.core.state import AgentState

# 原有方式 - 继续可用
db = await get_db_async()

# 保存会话（单用户）
session_id = "session_001"
state = AgentState(
    session_id=session_id,
    title="我的对话"
)
await db.save_state(session_id, state.model_dump())

# 加载会话
state_data = await db.load_state(session_id)
state = AgentState(**state_data) if state_data else None

# 列出所有会话
sessions = await db.list_sessions()
```

**特点**：
- ✅ 无需修改代码
- ✅ 所有会话混在一起
- ✅ 适合单用户场景

---

### 场景 2：多用户应用（新方式）

**适用**：Web 应用、多租户系统

```python
from assistant.db import get_db
from assistant.core.state import AgentState

# 获取数据库
db = await get_db_async()

# 为不同用户创建会话
user_a = "alice"
user_b = "bob"

# 用户 A 的会话
session_a1 = f"{user_a}_session_001"
state_a1 = AgentState(
    session_id=session_a1,
    user_id=user_a,  # ← 关键：设置 user_id
    title="Alice 的对话 1"
)
await db.save_state_for_user(user_a, session_a1, state_a1.model_dump())

# 用户 B 的会话
session_b1 = f"{user_b}_session_001"
state_b1 = AgentState(
    session_id=session_b1,
    user_id=user_b,  # ← 关键：设置 user_id
    title="Bob 的对话 1"
)
await db.save_state_for_user(user_b, session_b1, state_b1.model_dump())

# 列出用户 A 的会话
alice_sessions = await db.list_sessions_for_user(user_a)
print(f"用户 A 有 {len(alice_sessions)} 个会话")

# 列出用户 B 的会话
bob_sessions = await db.list_sessions_for_user(user_b)
print(f"用户 B 有 {len(bob_sessions)} 个会话")

# 权限隔离：用户 A 无法访问用户 B 的会话
# ✅ 自动隔离
state = await db.load_state_for_user(user_a, session_b1)
# 返回 None - 用户 A 无法访问用户 B 的会话
```

**特点**：
- ✅ 用户会话完全隔离
- ✅ 按用户查询会话
- ✅ 支持用户统计
- ✅ 支持批量删除

---

### 场景 3：混合使用（平滑迁移）

**适用**：逐步从单用户迁移到多用户

```python
from assistant.db import get_db
from assistant.core.state import AgentState

db = await get_db_async()

# 方式 1：原有接口（旧会话）
old_session = "legacy_session_001"
await db.save_state(old_session, {...})

# 方式 2：新接口（新会话）
user_id = "user123"
new_session = f"{user_id}_session_001"
await db.save_state_for_user(user_id, new_session, {...})

# 方式 3：在 state 中设置 user_id（自动使用新逻辑）
state = AgentState(
    session_id="session_with_user",
    user_id=user_id,  # ← 自动触发多用户逻辑
    title="自动多用户"
)
await db.save_state(state.session_id, state.model_dump())
# 内部自动调用 save_state_for_user

# 所有方式都同时可用！
all_sessions = await db.list_sessions()  # 所有会话
user_sessions = await db.list_sessions_for_user(user_id)  # 特定用户的会话
```

**特点**：
- ✅ 旧代码和新代码共存
- ✅ 可以逐步迁移
- ✅ 无需一次性重写

---

## Agent 层面的使用

### 方式 1：单用户模式（默认）

**文件**: `src/assistant/core/agent.py`

```python
class MicroAgent:
    def __init__(self, config_path: str):
        self.db = get_db()

    async def run_task(self, session_id: str, user_input: str):
        """原有方式 - 不需要 user_id"""
        state_data = await self.db.load_state(session_id)
        state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)
        # ... 正常处理
        await self.db.save_state(state.session_id, state.model_dump())
```

**使用**：
```python
agent = MicroAgent("config.yaml")

# 单用户使用
await agent.run_task("session_001", "你好")
```

**特点**：
- ✅ 无需修改 Agent 代码
- ✅ 原有逻辑完全不变
- ✅ 继续使用 `save_state(session_id, state)`

---

### 方式 2：多用户模式（扩展）

**文件**: `src/assistant/core/agent.py`

```python
class MicroAgent:
    def __init__(self, config_path: str):
        self.db = get_db()

    async def run_task(
        self,
        session_id: str,
        user_input: str,
        user_id: Optional[str] = None  # ← 新增参数
    ):
        """支持 user_id 的多用户模式"""
        if user_id:
            # 多用户模式
            state_data = await self.db.load_state_for_user(user_id, session_id)
            if state_data:
                state = AgentState(**state_data)
            else:
                state = AgentState(session_id=session_id, user_id=user_id)
        else:
            # 单用户模式（原有逻辑）
            state_data = await self.db.load_state(session_id)
            state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)

        # ... 正常处理
        if user_id:
            await self.db.save_state_for_user(user_id, state.session_id, state.model_dump())
        else:
            await self.db.save_state(state.session_id, state.model_dump())
```

**使用**：
```python
agent = MicroAgent("config.yaml")

# 单用户使用（原有方式）
await agent.run_task("session_001", "你好")

# 多用户使用（新方式）
await agent.run_task("alice_session_001", "你好", user_id="alice")
await agent.run_task("bob_session_001", "你好", user_id="bob")

# 权限隔离
await agent.run_task("alice_session_001", "你好", user_id="bob")
# 用户 Bob 无法访问 Alice 的会话，自动创建新会话或返回错误
```

**特点**：
- ✅ 不破坏原有逻辑
- ✅ 通过参数控制模式
- ✅ 向后兼容
- ✅ 自动权限隔离

---

### 方式 3：自动多用户（推荐）

**文件**: `src/assistant/core/agent.py`

```python
class MicroAgent:
    def __init__(self, config_path: str, default_user_id: Optional[str] = None):
        self.default_user_id = default_user_id
        self.db = get_db()

    async def run_task(
        self,
        session_id: str,
        user_input: str,
        user_id: Optional[str] = None  # 可选参数
    ):
        """智能模式 - 自动选择"""
        # 优先使用传入的 user_id
        effective_user_id = user_id or self.default_user_id

        if effective_user_id:
            # 多用户模式
            state_data = await self.db.load_state_for_user(effective_user_id, session_id)
            if state_data:
                state = AgentState(**state_data)
                state.user_id = effective_user_id
            else:
                state = AgentState(
                    session_id=session_id,
                    user_id=effective_user_id
                )
        else:
            # 单用户模式
            state_data = await self.db.load_state(session_id)
            state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)

        # ... 处理逻辑

        # 保存
        if effective_user_id:
            await self.db.save_state_for_user(effective_user_id, state.session_id, state.model_dump())
        else:
            await self.db.save_state(state.session_id, state.model_dump())
```

**使用**：
```python
# 方式 1：全局默认用户
agent = MicroAgent("config.yaml", default_user_id="app_user")

# 所有请求自动使用 app_user
await agent.run_task("session_001", "你好")

# 方式 2：临时覆盖
await agent.run_task("session_002", "你好", user_id="temp_user")

# 方式 3：完全控制
agent = MicroAgent("config.yaml")  # 不设置默认用户

# 根据 session_id 推导 user_id
user_id = session_id.split('_')[0] if '_' in session_id else None
await agent.run_task(session_id, "你好", user_id=user_id)
```

---

## API 层面的使用

### FastAPI 路由示例

**文件**: `src/assistant/api/routes.py`

```python
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

router = APIRouter()

# ===== 单用户路由（原有方式）=====

@router.post("/chat/{session_id}")
async def chat_single_user(
    session_id: str,
    message: str,
    stream: bool = False
):
    """单用户聊天 - 原有接口"""
    agent = get_agent()
    await agent.run_task(session_id, message)
    return {"status": "success"}

@router.get("/sessions")
async def list_all_sessions():
    """列出所有会话 - 原有接口"""
    db = await get_db_async()
    sessions = await db.list_sessions()
    return {"sessions": sessions}

# ===== 多用户路由（新接口）=====

@router.post("/users/{user_id}/chat/{session_id}")
async def chat_multi_user(
    user_id: str,
    session_id: str,
    message: str,
    stream: bool = False
):
    """多用户聊天 - 新接口"""
    agent = get_agent()
    # 传入 user_id
    await agent.run_task(session_id, message, user_id=user_id)
    return {"status": "success"}

@router.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str):
    """列出用户的会话 - 新接口"""
    db = await get_db_async()
    sessions = await db.list_sessions_for_user(user_id)
    return {"user_id": user_id, "sessions": sessions}

@router.get("/users/{user_id}/stats")
async def get_user_statistics(user_id: str):
    """用户统计 - 新接口"""
    db = await get_db_async()
    stats = await db.get_user_stats(user_id)
    return stats

@router.delete("/users/{user_id}")
async def delete_user_data(user_id: str):
    """删除用户数据 - 新接口"""
    db = await get_db_async()
    count = await db.delete_user_sessions(user_id)
    return {"deleted": count}

# ===== 智能路由（自动检测）=====

@router.post("/chat/{session_id}")
async def chat_smart(
    session_id: str,
    message: str,
    user_id: Optional[str] = None  # 可选参数
):
    """智能聊天 - 自动检测是否需要 user_id"""
    agent = get_agent()
    # 传入 user_id（可选）
    await agent.run_task(session_id, message, user_id=user_id)
    return {"status": "success"}
```

**使用对比**：

```bash
# 单用户方式（原有）
curl -X POST http://localhost:8400/chat/session001 \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 多用户方式（新）
curl -X POST http://localhost:8400/users/alice/chat/session001 \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 智能方式（自动检测）
curl -X POST http://localhost:8400/chat/session001 \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "user_id": "alice"}'
```

---

## 迁移策略

### 阶段 1：数据库迁移（一次性）

```bash
cd assistant

# 备份现有数据库
cp museum_assistant.db museum_assistant.db.backup

# 执行迁移（添加 user_id 字段）
python -m assistant.db.migrations

# 验证迁移
python -m assistant.db.migrations --check
# 应该显示："✅ Already migrated"
```

### 阶段 2：保持现有代码运行（无修改）

现有代码继续工作：
```python
# 原有代码 - 无需修改
await db.save_state(session_id, state)
await db.load_state(session_id)
```

### 阶段 3：添加新功能（可选）

在需要的地方添加多用户支持：
```python
# 新功能 - 使用多用户接口
await db.save_state_for_user(user_id, session_id, state)
await db.list_sessions_for_user(user_id)
```

### 阶段 4：逐步迁移现有代码（可选）

逐步将关键代码迁移到多用户模式：
```python
# 逐步迁移
if user_id:
    await db.save_state_for_user(user_id, session_id, state)
else:
    await db.save_state(session_id, state)
```

### 阶段 5：完全迁移（可选）

最终完全使用多用户模式：
```python
# 完全迁移
await db.save_state_for_user(user_id, session_id, state)
```

---

## 最佳实践

### 1. Session ID 命名规范

```python
# 推荐格式：user_id + 唯一标识
session_id = f"{user_id}_{timestamp}_{random_id}"

# 示例
alice_session = "alice_1704096000_abc123"
bob_session = "bob_1704096001_def456"

# 优势：
# - 易于识别用户
# - 易于提取 user_id
# - 避免冲突
```

### 2. User ID 来源

```python
# 方式 1：从认证系统获取
user_id = get_current_user_id()

# 方式 2：从 session_id 推导
user_id = session_id.split('_')[0]

# 方式 3：从 token 解析
user_id = decode_token(token)

# 方式 4：使用默认用户
user_id = "default_user"
```

### 3. 错误处理

```python
try:
    state = await db.load_state_for_user(user_id, session_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found for user {user_id}"
        )
except Exception as e:
    logger.error(f"Failed to load session: {e}")
    raise HTTPException(status_code=500, detail="Internal error")
```

### 4. 性能优化

```python
# 批量查询
sessions = await db.list_sessions_for_user(user_id, limit=20)

# 使用统计缓存
stats = await db.get_user_stats(user_id)

# 定期清理旧会话
if len(sessions) > 1000:
    old_sessions = sessions[-100:]
    for session in old_sessions:
        await db.delete_state(session["id"])
```

---

## 总结

### ✅ 不会废弃的内容

1. **原有接口完全保留**
   - `save_state(session_id, state)`
   - `load_state(session_id)`
   - `list_sessions()`
   - `delete_state(session_id)`

2. **原有逻辑完全不变**
   - Agent 的核心逻辑不变
   - 只需可选地添加 user_id 参数

3. **原有数据库完全兼容**
   - 自动迁移添加 user_id
   - 现有数据不受影响

### ✅ 新增内容

1. **新的数据库接口**
   - `save_state_for_user(user_id, session_id, state)`
   - `load_state_for_user(user_id, session_id)`
   - `list_sessions_for_user(user_id)`
   - `delete_user_sessions(user_id)`
   - `get_user_stats(user_id)`

2. **新的 API 路由**
   - `/users/{user_id}/chat/{session_id}`
   - `/users/{user_id}/sessions`
   - `/users/{user_id}/stats`
   - `/users/{user_id}`

3. **新的管理功能**
   - 用户会话隔离
   - 用户统计
   - 批量删除
   - 分页查询

### 🎯 使用建议

**单用户应用**：
- 继续使用原有接口
- 无需任何修改

**多用户应用**：
- 执行数据库迁移
- 使用新接口 `save_state_for_user` 等
- 添加用户认证

**混合应用**：
- 原有功能继续使用旧接口
- 新功能使用新接口
- 逐步迁移，无需一次性重写
