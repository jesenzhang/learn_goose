# 多用户会话管理 - 总结

## 当前状态

**❌ 不支持多用户会话管理**

### 当前数据库结构

```sql
-- sessions 表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,           -- 只有 session_id
    state TEXT NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
-- ❌ 问题：缺少 user_id 字段
```

### 当前查询问题

| 操作 | 问题 |
|------|------|
| `list_sessions()` | 返回所有会话，无法按用户过滤 |
| `load_state(session_id)` | 只通过 session_id 加载，无法验证用户权限 |
| `delete_state(session_id)` | 只删除单个会话，无法按用户批量删除 |

## 改进方案

### 1. 数据库表升级

**添加 user_id 字段：**

```sql
-- 步骤 1：添加列
ALTER TABLE sessions ADD COLUMN user_id TEXT;

-- 步骤 2：创建索引
CREATE INDEX idx_sessions_user ON sessions(user_id, updated_at DESC);

-- 步骤 3：迁移现有数据
UPDATE sessions SET user_id = 'default' WHERE user_id IS NULL;
```

### 2. 新增多用户接口

```python
# 为指定用户保存会话
await db.save_state_for_user(user_id, session_id, state)

# 加载指定用户的会话
state = await db.load_state_for_user(user_id, session_id)

# 列出指定用户的会话
sessions = await db.list_sessions_for_user(user_id, limit=10)

# 删除用户的所有会话
count = await db.delete_user_sessions(user_id)

# 获取用户统计
stats = await db.get_user_stats(user_id)

# 列出所有用户
users = await db.list_all_users()

# 全局统计
global_stats = await db.get_global_stats()
```

### 3. 迁移脚本

```bash
# 检查迁移状态
python -m assistant.db.migrations --check

# 执行迁移
python -m assistant.db.migrations

# 指定数据库路径
python -m assistant.db.migrations museum_assistant.db

# 回滚迁移（危险操作！）
python -m assistant.db.migrations --rollback
```

### 4. 使用示例

```python
from assistant.db import get_db
from assistant.core.state import AgentState

# 获取数据库
db = await get_db_async()

# 为用户创建会话
user_id = "user123"
session_id = f"{user_id}_session_001"
state = AgentState(
    session_id=session_id,
    user_id=user_id,
    title="我的对话"
)
await db.save_state_for_user(user_id, session_id, state.model_dump())

# 列出用户的会话
user_sessions = await db.list_sessions_for_user(user_id)
for session in user_sessions:
    print(f"- {session['id']}: {session['title']}")

# 获取用户统计
stats = await db.get_user_stats(user_id)
print(f"统计: 会话={stats['sessions']}, 事件={stats['events']}")

# 删除用户数据
deleted = await db.delete_user_sessions(user_id)
print(f"删除了 {deleted} 个会话")
```

## 实现文件

### 新增文件

1. **MULTI_USER_DB_IMPROVEMENTS.md** - 详细改进方案文档
2. **src/assistant/db/migrations.py** - 数据库迁移脚本
3. **src/assistant/db/multi_user_manager.py** - 多用户数据库管理器
4. **multi_user_example.py** - 使用示例代码

### 修改文件

1. **src/assistant/db/async_manager.py** - 添加迁移检查
2. **src/assistant/db/protocol.py** - 扩展协议支持多用户
3. **src/assistant/core/state.py** - 添加 user_id 字段

## 快速开始

### 步骤 1：执行数据库迁移

```bash
cd assistant

# 检查是否需要迁移
python -m assistant.db.migrations --check

# 执行迁移
python -m assistant.db.migrations
```

### 步骤 2：使用多用户功能

```python
from assistant.db import MultiUserAsyncDatabaseManager

# 创建多用户数据库管理器
db = MultiUserAsyncDatabaseManager("museum_assistant.db")
await db.initialize()

# 为用户保存会话
await db.save_state_for_user("user1", "session1", {...})

# 列出用户的会话
sessions = await db.list_sessions_for_user("user1")
```

## 向后兼容性

### 现有接口保持可用

```python
# 现有代码继续工作
await db.save_state(session_id, state)
await db.load_state(session_id)
await db.list_sessions()
```

### 自动迁移

- 数据库初始化时自动检查是否需要迁移
- 如果需要，自动添加 user_id 字段
- 为现有数据设置默认用户 ID

## API 变更

### 新增 API

```python
# FastAPI 路由示例

@app.get("/users")
async def list_users():
    """列出所有用户"""
    db = await get_db_async()
    users = await db.list_all_users()
    return {"users": users}

@app.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str):
    """列出用户的会话"""
    db = await get_db_async()
    sessions = await db.list_sessions_for_user(user_id)
    return {"user_id": user_id, "sessions": sessions}

@app.get("/users/{user_id}/stats")
async def get_user_stats(user_id: str):
    """获取用户统计"""
    db = await get_db_async()
    stats = await db.get_user_stats(user_id)
    return stats

@app.delete("/users/{user_id}")
async def delete_user_data(user_id: str):
    """删除用户数据"""
    db = await get_db_async()
    count = await db.delete_user_sessions(user_id)
    return {"deleted": count}
```

## 性能优化

1. **索引优化**
   - `idx_sessions_user(user_id, updated_at DESC)` - 加速用户查询
   - 避免全表扫描

2. **分页查询**
   - 支持 `limit` 和 `offset` 参数
   - 减少内存使用

3. **连接池**
   - 异步连接复用
   - 减少连接开销

## 权限隔离

### 用户级隔离

```python
# 用户 A 无法访问用户 B 的会话
user_a = "alice"
user_b = "bob"

# 用户 A 尝试访问用户 B 的会话
session_id = f"{user_b}_secret"
state = await db.load_state_for_user(user_a, session_id)
# 返回 None - 权限隔离
```

## 数据迁移策略

### 阶段 1：添加字段
- 使用 `ALTER TABLE` 添加 user_id
- 不影响现有功能

### 阶段 2：扩展接口
- 添加多用户接口
- 保持旧接口可用

### 阶段 3：逐步迁移
- 新代码使用多用户接口
- 旧代码继续使用旧接口

### 阶段 4：完全迁移（可选）
- 标记旧接口为 deprecated
- 计划未来版本移除

## 测试建议

1. **迁移测试**
   - 测试添加 user_id 字段
   - 测试现有数据迁移
   - 测试回滚功能

2. **功能测试**
   - 测试用户会话创建
   - 测试用户会话查询
   - 测试用户数据删除

3. **隔离测试**
   - 测试用户权限隔离
   - 测试跨用户访问失败

4. **性能测试**
   - 测试大量用户查询
   - 测试大量会话管理

## 注意事项

1. **数据库文件路径**
   - 确保数据库文件可写
   - 建议使用绝对路径

2. **迁移备份**
   - 迁移前备份数据库
   - 使用 `db.backup()` 备份

3. **并发安全**
   - 使用事务确保一致性
   - 处理并发更新冲突

4. **错误处理**
   - 捕获迁移失败
   - 提供回滚选项

## 故障排除

### 迁移失败

```bash
# 检查数据库文件权限
ls -la museum_assistant.db

# 尝试手动迁移
sqlite3 museum_assistant.db "ALTER TABLE sessions ADD COLUMN user_id TEXT;"

# 检查表结构
sqlite3 museum_assistant.db ".schema sessions"
```

### 查询失败

```python
# 检查迁移是否成功
conn = await db._get_connection()
cursor = await conn.execute("PRAGMA table_info(sessions)")
columns = await cursor.fetchall()
print([col[1] for col in columns])
# 应该包含 'user_id'
```

## 总结

### 改进内容

- ✅ 添加 user_id 到 sessions 表
- ✅ 创建用户索引
- ✅ 扩展 DatabaseProtocol
- ✅ 实现多用户查询接口
- ✅ 保持向后兼容
- ✅ 提供迁移脚本

### 新增功能

- 按用户列出会话
- 用户统计信息
- 批量删除用户会话
- 用户权限隔离
- 全局用户管理

### 文件清单

1. `MULTI_USER_DB_IMPROVEMENTS.md` - 方案文档
2. `src/assistant/db/migrations.py` - 迁移脚本
3. `src/assistant/db/multi_user_manager.py` - 多用户管理器
4. `multi_user_example.py` - 使用示例

### 下一步

1. 执行数据库迁移
2. 更新 API 路由支持用户
3. 添加用户认证
4. 完善测试用例
5. 更新文档
