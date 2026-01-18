# 前端客户端适配更新说明

> **日期**: 2025-01-17
> **版本**: 1.0
> **目标**: 说明 skill_micro_client2.py 适配新的 messages 表架构

---

## 1. 更新概述

数据库架构从 **history 存储在 state 中** 改为 **独立的 messages 表**。

### 之前的设计
```python
# state.history 存储在 sessions.state TEXT 字段（JSON）
{
    "history": [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ],
    ...
}
```

### 现在的设计
```python
# messages 独立存储在 messages 表
# CREATE TABLE messages (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     session_id INTEGER NOT NULL,
#     role TEXT NOT NULL,
#     content TEXT NOT NULL,
#     metadata TEXT,
#     timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# )

# state.history 通过 API 端点动态加载
{
    "history": [
        {"role": "user", "content": "Hello", "metadata": {}},
        {"role": "assistant", "content": "Hi there!", "metadata": {}},
        ...
    ]
}
```

---

## 2. API 变更

### 2.1 新增 get_messages 接口

**AsyncDatabaseManager**
```python
async def get_messages(self, session_id: int) -> List[Dict[str, Any]]:
    """获取会话的所有消息"""
    # 按 timestamp ASC 排序（从旧到新）
    # 返回完整的消息对象
```

**RemoteDatabaseManager**
```python
async def get_messages(self, session_id: int) -> List[Dict[str, Any]]:
    """通过 API 获取会话的所有消息"""
    # API: GET /agent/{session_id}/messages
```

**DatabaseBase (抽象基类)**
```python
@abstractmethod
async def get_messages(self, session_id: int) -> List[Dict[str, Any]]:
    """获取会话的所有消息"""
    pass
```

### 2.2 更新 get_session_state 端点

**路径**: `GET /agent/{session_id}/state`

**返回值变化**：
- **之前**: state.history 从 state 表的 JSON 字段加载
- **现在**: state.history 从 messages 表动态加载

**实现细节**:
```python
@router.get("/agent/{session_id}/state")
async def get_session_state(session_id: int):
    db = get_db()
    state_data = await db.load_state(session_id)
    
    # 从 messages 表加载历史
    messages = await db.get_messages(session_id)
    
    # 转换为 history 格式
    history = []
    for msg in messages:
        history.append({
            "role": msg["role"],
            "content": msg["content"],
            "metadata": msg.get("metadata", {})
        })
    
    # 填充到 state
    state_data["history"] = history
    
    state = AgentState(**state_data)
    return state.model_dump()
```

---

## 3. 技能影响

### 3.1 无需修改的代码

**skill_micro_client2.py** - 前端客户端
```python
# 以下代码无需修改，继续正常工作：

def load_history_from_server(session_id: str):
    state = load_session_state(session_id)
    if not state:
        return
    
    # 从 state.history 读取历史（API 已动态加载）
    for msg in state.get("history", []):
        if msg["role"] in ("user", "assistant") and msg.get("content"):
            st.session_state.chat_history.append(msg)
```

**reason**: API 接点保持向后兼容，`state.history` 字段继续存在，只是加载来源从 state 表改为 messages 表。

### 3.2 Agent 内部变化

**agent.py - Agent 运行时**
```python
# 发送消息时（保持不变）
await self.add_message(session_id, Message.assistant(response), state)

# Agent 内部不再操作 state.history
# state.history 仅通过 get_messages 查询获取
```

---

## 4. 数据结构变化

### 4.1 Sessions 表
```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    state TEXT NOT NULL,         -- JSON，不再包含 history
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 Messages 表（新增）
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,         -- user, assistant, system, tool
    content TEXT NOT NULL,
    metadata TEXT,                  -- JSON
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session ON messages(session_id, timestamp DESC);
```

### 4.3 Events 表
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

---

## 5. 使用流程

### 5.1 客户端流程

```
1. 创建会话
   skill_micro_client2.py: create_new_session()
   → API: POST /session/{title}
   → DB: 创建 sessions 记录，返回 session_id

2. 加载会话状态
   skill_micro_client2.py: load_history_from_server(session_id)
   → API: GET /agent/{session_id}/state
   → DB: 加载 sessions.state + 从 messages 表加载 history
   → 返回: AgentState (包含 history 字段)

3. 显示历史
   for msg in st.session_state.chat_history:
       st.chat_message(**msg)

4. 发送新消息
   skill_micro_client2.py: send_message()
   → API: POST /chat/{session_id}
   → DB: 调用 add_message 保存到 messages 表

5. 重新加载历史（可选）
   skill_micro2_client2.py: load_history_from_server(session_id)
   → 重新获取完整历史
```

### 5.2 服务端流程

```
1. Agent 运行
   agent.run_task(session_id, ...)
   → 保存 state (sessions.state)
   → 发送消息时调用 add_message (messages 表)

2. API 端点
   GET /agent/{session_id}/state
   → 加载 sessions.state
   → 调用 get_messages (messages 表)
   → 合并返回 state

3. 数据库操作
   save_state → 写入 sessions.state
   add_message → 写入 messages 表
   get_messages → 从 messages 表查询
   delete_session → CASCADE 删除关联的 messages
```

---

## 6. 兼容性保证

### 6.1 API 层面

✅ **向后兼容**：
- `GET /agent/{session_id}/state` 端点保持不变
- 返回值格式保持不变（包含 history 字段）
- 前端代码无需修改

✅ **前端无需修改**：
- skill_micro_client2.py 无需任何修改
- 继续使用 `state.get("history", [])` 读取历史
- 格式完全一致

### 6.2 数据库层面

✅ **分离清晰**：
- **sessions.state** - 会话状态（不含 history）
- **messages 表** - 独立消息存储
- **events 表** - 系统事件（独立）

✅ **查询优化**：
- messages 表有索引 `(session_id, timestamp)`
- 支持 ORDER BY 快速查询
- 按会话和时间排序

✅ **级联删除**：
- 删除 sessions 时自动删除关联的 messages
- 保持数据一致性

---

## 7. 性能影响

### 7.1 读取性能

**之前**：
- 单次查询：`SELECT state FROM sessions WHERE id = ?`
- JSON 解析：`json.loads(state["history"])`

**现在**：
- 两次查询：
  1. `SELECT state FROM sessions WHERE id = ?`
  2. `SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC`
- 更灵活，但可能有轻微性能损失

**优化建议**：
- 对话话历史少的场景，性能影响可以忽略
- 对话话历史多的场景，可以考虑缓存

### 7.2 写入性能

**之前**：
- 每次消息都序列化 history 到 state JSON
- state 可能变得很大

**现在**：
- 每次消息只插入一条记录到 messages 表
- state 保持相对较小

**优化建议**：
- 减少每次更新的数据量
- 批量插入可以使用事务

---

## 8. 测试验证

### 8.1 功能测试

- [ ] 创建新会话
- [ ] 发送消息
- [ ] 加载会话状态
- [ ] 查看历史消息
- [ ] 删除会话

### 8.2 API 测试

```bash
# 创建会话
curl -X POST "http://localhost:8400/session/Test Chat"

# 发送消息
curl -X POST "http://localhost:8400/chat/123" \
   -H "Content-Type: application/json" \
   -d '{"message": "Hello"}'

# 获取状态
curl -X GET "http://localhost:8400/agent/123/state"

# 验证 history 字段存在且格式正确
```

### 8.3 前端测试

1. 启动 skill_micro_client2.py
2. 登录或进入客模式
3. 创建新会话
4. 发送几条消息
5. 刷新页面，验证历史显示正确
6. 检查控制台无错误

---

## 9. 迁移检查清单

### 9.1 数据库层面

- [ ] sessions 表结构已更新
- [ ] messages 表已创建
- [ ] 旧数据迁移已完成（如果有）
- [ ] 外键约束正确配置
- [ ] 索引已创建

### 9.2 API 层面

- [ ] get_messages 在 AsyncDatabaseManager 实现
- [ ] get_messages 在 RemoteDatabaseManager 实现
- [ ] get_session_state 已更新
- [ ] API 端点测试通过

### 9.3 前端层面

- [ ] skill_micro_client2.py 无需修改
- [ ] load_history_from_server 正常工作
-  - 验证历史正确显示
- - 验证消息顺序正确（时间顺序）

---

## 10. 回滚计划

如果出现问题，回滚方案：

### 10.1 数据库回滚

```sql
-- 删除 messages 表
DROP TABLE IF EXISTS messages;

-- 恢复旧结构（如果需要）
-- sessions.state 继续包含 history
```

### 10.2 代码回滚

```python
# 回退到旧版本：
git checkout <commit-hash>

# 或者删除 messages 表相关代码：
# rm async_manager.py 中的 messages 表创建
# 删除 add_message 和 get_messages 方法
# 恢复旧版本的 save_state（包含 history 序列化）
```

---

## 11. 相关文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/assistant/db/base.py` | 新增 | DatabaseBase 抽象基类 |
| `src/assistant/db/async_manager.py` | 修改 | 添加 messages 表和 get_messages 方法 |
| `src/assistant/db/remote_db.py` | 修改 | 添加 get_messages 方法 |
| `src/assistant/db/factory.py` | 修改 | 返回 DatabaseBase 类型 |
| `src/assistant/db/__init__.py` | 修改 | 删除 UnifiedDatabase |
| `src/assistant/api/routes.py` | 修改 | 更新 get_session_state 端点 |
| `src/assistant/main.py` | 修改 | 使用工厂模式 |
| `skill_micro_client2.py` | 无需修改 | 继续使用 state.history |

---

## 12. 总结

### 核心变更

1. ✅ **架构简化**：删除 UnifiedDatabase 代理层，使用工厂模式
2. ✅ **数据分离**：history 从 state 独立为 messages 表
3. ✅ **前端兼容**：skill_micro_client2.py 无需任何修改
4. ✅ **接口对齐**：AsyncDatabaseManager 和 RemoteDatabaseManager 都实现 get_messages

### 优势

1. ✅ 数据结构更清晰
2. ✅ 查询更灵活
3. ✅ 便于扩展（如按时间范围查询）
4. ✅ 减少序列化开销
5. ✅ 支持大数据量历史（state 不会过大）

### 注意事项

1. ✅ 保持向后兼容：API 端点格式不变
2. ✅ 前端无需修改：继续使用 state.history
3. ⚠️ 性能监控：关注数据库查询性能
4. ⚠️ 数据迁移：如果有历史数据，需要正确迁移

---

**文档版本**: 1.0
**状态**: 已完成
**下一步**: 测试验证
