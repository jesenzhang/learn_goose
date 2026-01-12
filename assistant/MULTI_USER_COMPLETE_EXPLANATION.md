# 多用户功能 - 完整说明

## 🎯 你的核心问题

| 问题 | 简短答案 |
|------|---------|
| **原有代码废弃了吗？** | ❌ 不会！所有原有接口完全保留 |
| **需要重写代码吗？** | ❌ 不需要！原有代码可以继续使用 |
| **新接口是替换吗？** | ❌ 不是！新接口是额外功能 |
| **迁移后数据会丢失吗？** | ❌ 不会！迁移是向后兼容的 |

---

## ✅ 核心原则

### 1. 向后兼容性保证

```python
# ✅ 这些接口**继续**正常工作，永远不会废弃
await db.save_state(session_id, state)
await db.load_state(session_id)
await db.list_sessions()
await db.delete_state(session_id)
```

### 2. 新接口是**扩展**，不是**替换**

```python
# ✅ 原有接口（继续工作）
await db.save_state("session_001", {...})

# ✅ 新接口（额外功能）
await db.save_state_for_user("alice", "session_001", {...})

# 两种方式同时可用！
```

---

## 🚀 快速开始

### 步骤 1：数据库迁移（一次性，只需做一次）

```bash
cd assistant

# 1. 备份现有数据库
cp museum_assistant.db museum_assistant.db.backup

# 2. 执行迁移（添加 user_id 字段）
python -m assistant.db.migrations

# 3. 验证迁移
python -m assistant.db.migrations --check
# 应该显示："✅ Already migrated"
```

**迁移做了什么**：
- ✅ 在 sessions 表添加 `user_id` 字段
- ✅ 创建 `user_id` 索引加速查询
- ✅ 为现有数据设置默认 user_id
- ✅ 原有数据完全保留

### 步骤 2：继续使用原有代码（无需修改）

```python
# 原有代码完全不变，继续使用
from assistant.db import get_db
from assistant.core.state import AgentState

db = await get_db_async()

# 保存会话（原有方式，继续可用）
session_id = "session_001"
state = AgentState(
    session_id=session_id,
    title="我的对话"
)
await db.save_state(session_id, state.model_dump())

# 加载会话（原有方式，继续可用）
state_data = await db.load_state(session_id)
state = AgentState(**state_data) if state_data else None

# 列出所有会话（原有方式，继续可用）
sessions = await db.list_sessions()
```

**注意**：
- ✅ 无需修改任何代码
- ✅ 所有功能继续工作
- ✅ 单用户应用保持不变

---

## 🔧 何时使用多用户功能

### 场景 1：继续使用单用户模式（推荐用于个人助手）

**适用**：个人助手、单用户系统

```python
# 继续使用原有接口，无需任何修改
db = await get_db_async()

await db.save_state("session_001", {...})
await db.load_state("session_001")
await db.list_sessions()
```

**特点**：
- ✅ 无需修改代码
- ✅ 所有会话在一起
- ✅ 适合单用户场景

---

### 场景 2：使用多用户模式（推荐用于 Web 应用）

**适用**：Web 应用、多租户系统、SaaS

```python
# 使用新接口
db = await get_db_async()

# 为不同用户创建会话
user_id = "alice"
session_id = f"{user_id}_session_001"
state = AgentState(
    session_id=session_id,
    user_id=user_id,  # ← 设置 user_id
    title="Alice 的对话 1"
)
await db.save_state_for_user(user_id, session_id, state.model_dump())

# 只列出该用户的会话
user_sessions = await db.list_sessions_for_user(user_id)
# 只包含 Alice 的会话

# 用户隔离：Bob 无法访问 Alice 的会话
# ✅ 自动隔离权限
```

**特点**：
- ✅ 用户会话完全隔离
- ✅ 按用户查询会话
- ✅ 用户权限隔离

---

### 场景 3：混合使用（平滑迁移）

**适用**：逐步从单用户迁移到多用户

```python
# 旧会话继续使用原有接口
await db.save_state("legacy_session_001", {...})

# 新会话使用多用户接口
await db.save_state_for_user("alice", "alice_session_001", {...})

# 两种方式同时可用
all_sessions = await db.list_sessions()  # 包含所有会话
alice_sessions = await db.list_sessions_for_user("alice")  # 只包含 Alice 的
```

**特点**：
- ✅ 新旧代码共存
- ✅ 可以逐步迁移
- ✅ 无需一次性重写

---

## 📖 详细文档

我创建了以下文档来帮助你：

### 1. **MULTI_USER_QUICK_REF.md** - 快速参考表
- 接口对比表
- 三种使用方式对比
- 迁移检查清单
- 常见误区

### 2. **MULTI_USER_USAGE_GUIDE.md** - 详细使用指南
- 向后兼容性设计
- 使用方式对比（3 种场景）
- Agent 层面的使用
- API 层面的使用
- 迁移策略（4 个阶段）

### 3. **multi_user_practical_examples.py** - 实际应用示例
- API 层面示例
- Agent 层面示例
- 实际应用场景（5 个）
- Session ID 管理
- 错误处理
- 最佳实践

---

## 💡 使用建议

### 对于单用户应用

```python
# 无需修改，继续使用原有接口
await db.save_state(session_id, state)
await db.load_state(session_id)
await db.list_sessions()
```

### 对于多用户应用

```python
# 使用新接口
await db.save_state_for_user(user_id, session_id, state)
await db.load_state_for_user(user_id, session_id)
await db.list_sessions_for_user(user_id)
```

### 对于迁移中的应用

```python
# 旧会话使用旧接口
await db.save_state("legacy_session_001", {...})

# 新会话使用新接口
await db.save_state_for_user("alice", "alice_session_001", {...})

# 两种方式都可用
all_sessions = await db.list_sessions()
user_sessions = await db.list_sessions_for_user("alice")
```

---

## 🔍 常见问题

### Q1：原有代码会被废弃吗？

**A**：❌ 不会！所有原有接口完全保留，可以继续使用。

### Q2：需要重写所有代码吗？

**A**：❌ 不需要！原有代码可以继续使用，新接口是额外功能。

### Q3：迁移后原有数据会丢失吗？

**A**：❌ 不会！迁移是向后兼容的，原有数据会自动添加默认 user_id。

### Q4：必须使用新接口吗？

**A**：❌ 不必须！你可以根据需要选择使用原有接口或新接口。

### Q5：新接口和旧接口可以混用吗？

**A**：✅ 可以！新旧接口可以同时使用，互不干扰。

---

## 📚 文档清单

| 文档 | 说明 |
|------|------|
| **MULTI_USER_QUICK_REF.md** | 快速参考表，接口对比 |
| **MULTI_USER_USAGE_GUIDE.md** | 详细使用指南，3 种场景 |
| **multi_user_practical_examples.py** | 实际代码示例 |
| **MULTI_USER_SUPPORT_SUMMARY.md** | 功能总结，快速开始 |

---

## ✅ 总结

### 不会废弃的内容

1. ✅ 所有原有数据库接口
2. ✅ 所有原有 Agent 逻辑
3. ✅ 所有原有 API 路由
4. ✅ 所有原有配置文件
5. ✅ 所有原有数据

### 新增内容

1. ✅ 多用户数据库接口
2. ✅ 用户统计功能
3. ✅ 用户权限隔离
4. ✅ 数据库迁移脚本
5. ✅ 实际应用示例

### 使用建议

- **单用户应用**：继续使用原有接口，无需修改
- **多用户应用**：使用新接口 `save_state_for_user` 等
- **迁移中应用**：新旧接口混用，逐步迁移
- **无需一次性重写**：保持向后兼容性
