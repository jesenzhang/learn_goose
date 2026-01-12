# 快速参考：多用户功能速查表

## 🎯 你的问题 & 答案

| 问题 | 答案 |
|------|------|
| **原有代码废弃了吗？** | ❌ 不会！所有原有接口完全保留 |
| **需要重写代码吗？** | ❌ 不需要！可以继续使用原有接口 |
| **新接口是替换吗？** | ❌ 不是！新接口是**额外功能** |
| **数据库迁移后原有数据会丢失吗？** | ❌ 不会！迁移是向后兼容的 |

---

## 📊 接口对比表

| 操作 | 原有接口（继续可用） | 新接口（多用户） |
|------|---------------------|----------------|
| 保存会话 | `save_state(session_id, state)` | `save_state_for_user(user_id, session_id, state)` |
| 加载会话 | `load_state(session_id)` | `load_state_for_user(user_id, session_id)` |
| 列出会话 | `list_sessions()` | `list_sessions_for_user(user_id)` |
| 删除会话 | `delete_state(session_id)` | `delete_user_sessions(user_id)` |
| 获取统计 | ❌ 无 | `get_user_stats(user_id)` |
| 列出用户 | ❌ 无 | `list_all_users()` |

---

## 🚀 三种使用方式

### 方式 1：继续使用原有接口（推荐用于单用户）

```python
# 完全不变，继续使用
db = await get_db_async()

# 保存会话
await db.save_state("session_001", {...})

# 加载会话
state = await db.load_state("session_001")

# 列出所有会话
sessions = await db.list_sessions()
```

**何时使用**：
- ✅ 单用户应用
- ✅ 个人助手
- ✅ 无需用户隔离的场景

---

### 方式 2：使用新接口（推荐用于多用户）

```python
# 新接口，多用户支持
db = await get_db_async()

# 为用户保存会话
await db.save_state_for_user("alice", "session_001", {...})

# 加载用户的会话
state = await db.load_state_for_user("alice", "session_001")

# 列出用户的会话
sessions = await db.list_sessions_for_user("alice")

# 获取用户统计
stats = await db.get_user_stats("alice")

# 删除用户数据
await db.delete_user_sessions("alice")
```

**何时使用**：
- ✅ Web 应用（多用户）
- ✅ 需要用户隔离的场景
- ✅ SaaS 应用

---

### 方式 3：混合使用（平滑迁移）

```python
# 新旧接口同时使用，逐步迁移

# 旧会话继续使用旧接口
await db.save_state("legacy_session_001", {...})

# 新会话使用新接口
await db.save_state_for_user("alice", "alice_session_001", {...})

# 两种方式都可以查询所有会话
all_sessions = await db.list_sessions()
# 包含：legacy_session_* + alice_session_* + bob_session_*

# 但只能查询特定用户的新会话
alice_sessions = await db.list_sessions_for_user("alice")
# 只包含：alice_session_*
```

**何时使用**：
- ✅ 从单用户迁移到多用户
- ✅ 需要兼容旧数据
- ✅ 渐进式升级

---

## 🔑 关键概念

### 1. user_id 在哪里？

**选项 1：在 state 中**
```python
state = {
    "session_id": "session_001",
    "user_id": "alice",  # ← 在这里
    "status": "idle"
}
# 自动触发多用户逻辑
await db.save_state(state["session_id"], state)
```

**选项 2：作为单独参数**
```python
# 显式传入 user_id
await db.save_state_for_user("alice", "session_001", {...})
```

**选项 3：从 session_id 推导**
```python
# session_id 格式：user_id + "_" + ...
session_id = "alice_session_001"
user_id = session_id.split('_')[0]  # 提取用户
```

---

### 2. Session ID 命名规范

推荐格式：`{user_id}_{timestamp}_{random}`

```python
import time
import uuid

# 好的命名
user_id = "alice"
session_id = f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
# 结果：alice_1704096000_abc12345

# 好处：
# ✅ 易于识别用户
# ✅ 避免冲突
# ✅ 天然按时间排序
# ✅ 易于提取 user_id
```

---

### 3. 权限隔离

```python
# 用户 A 尝试访问用户 B 的会话
state = await db.load_state_for_user("alice", "bob_session_001")
# 返回 None - 自动隔离权限
```

---

## 📋 迁移检查清单

### 阶段 1：数据库迁移（必须）

```bash
cd assistant

# 1. 备份现有数据库
cp museum_assistant.db museum_assistant.db.backup

# 2. 执行迁移
python -m assistant.db.migrations

# 3. 验证迁移
python -m assistant.db.migrations --check
# 应该显示："✅ Already migrated"
```

**验证方法**：
```python
# 检查 user_id 字段是否添加成功
conn = await db._get_connection()
cursor = await conn.execute("PRAGMA table_info(sessions)")
columns = await cursor.fetchall()
column_names = [col[1] for col in columns]
print(column_names)
# 应该包含：'user_id'
```

---

### 阶段 2：保持现有代码运行（无需修改）

```python
# 原有代码继续工作，无需任何修改
from assistant.db import get_db

db = await get_db_async()

# 原有接口完全可用
await db.save_state("session_001", {...})
await db.load_state("session_001")
await db.list_sessions()
```

**无需修改**：
- ✅ Agent 代码
- ✅ API 路由
- ✅ 工具函数
- ✅ 配置文件

---

### 阶段 3：添加新功能（可选）

在需要的地方添加多用户支持：

```python
# 示例：添加用户统计路由
@router.get("/users/{user_id}/stats")
async def get_user_stats(user_id: str):
    db = await get_db_async()
    stats = await db.get_user_stats(user_id)
    return stats

# 示例：添加用户会话列表路由
@router.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str):
    db = await get_db_async()
    sessions = await db.list_sessions_for_user(user_id)
    return {"sessions": sessions}
```

---

### 阶段 4：逐步迁移（可选）

根据需要逐步迁移关键代码：

```python
# 旧代码
def old_function(session_id):
    state = await db.load_state(session_id)
    return state

# 新代码（多用户支持）
def new_function(user_id, session_id):
    state = await db.load_state_for_user(user_id, session_id)
    return state

# 混合代码（同时支持）
def hybrid_function(user_id=None, session_id=None):
    if user_id:
        return await db.load_state_for_user(user_id, session_id)
    else:
        return await db.load_state(session_id)
```

---

## 💡 最佳实践

### 1. 选择合适的使用方式

```python
# 个人助手：使用原有接口
await db.save_state("session_001", {...})

# Web 应用：使用新接口
await db.save_state_for_user(current_user_id, session_id, {...})

# 迁移中：混合使用
if has_user_id:
    await db.save_state_for_user(user_id, session_id, {...})
else:
    await db.save_state(session_id, {...})
```

### 2. 错误处理

```python
# 原有接口：session_id 不存在
state = await db.load_state("unknown_session")
# 返回 None - 正常行为

# 新接口：用户会话不存在
state = await db.load_state_for_user("alice", "unknown_session")
# 返回 None - 正常行为
```

### 3. Session ID 管理

```python
import time
import uuid

def generate_session_id(user_id: str) -> str:
    """生成会话 ID"""
    return f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

# 使用
user_id = "alice"
session_id = generate_session_id(user_id)
# 结果：alice_1704096000_abc12345
```

### 4. 性能优化

```python
# 使用分页
sessions = await db.list_sessions_for_user(user_id, limit=20)

# 使用统计缓存
stats = await db.get_user_stats(user_id)

# 定期清理
if len(sessions) > 100:
    old_sessions = sessions[-100:]
    for session in old_sessions:
        await db.delete_state(session["id"])
```

---

## ⚠️ 常见误区

### 误区 1：必须使用新接口

**真相**：
- ❌ 不必须使用新接口
- ✅ 原有接口继续完全可用
- ✅ 可以按需选择使用

### 误区 2：迁移后会丢失数据

**真相**：
- ❌ 不会丢失数据
- ✅ 迁移是向后兼容的
- ✅ 原有数据自动添加默认 user_id

### 误区 3：必须重写所有代码

**真相**：
- ❌ 不需要重写
- ✅ 可以逐步迁移
- ✅ 新旧代码可以共存

### 误区 4：session_id 必须包含 user_id

**真相**：
- ❌ 不必须
- ✅ 可以通过参数传递 user_id
- ✅ 也可以在 state 中设置 user_id

---

## ✅ 总结

### 不会废弃的内容

1. ✅ 所有原有数据库接口
2. ✅ 所有原有 Agent 逻辑
3. ✅ 所有原有 API 路由
4. ✅ 所有原有配置文件

### 新增内容

1. ✅ 多用户数据库接口
2. ✅ 用户统计功能
3. ✅ 用户权限隔离
4. ✅ 数据库迁移脚本

### 使用建议

1. **单用户**：继续使用原有接口
2. **多用户**：使用新接口 `save_state_for_user` 等
3. **迁移中**：混合使用两种接口
4. **逐步升级**：根据需要选择合适的接口
