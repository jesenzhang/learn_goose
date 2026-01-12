# 多用户会话管理改进方案

## 概述

当前数据库设计不支持多用户会话管理，需要进行表结构升级和接口改进。

## 当前问题

1. **sessions 表缺少 user_id 字段**
   - 无法区分不同用户的会话
   - 无法按用户过滤查询
   - 无法验证用户权限

2. **接口不支持用户维度**
   - `list_sessions()` 返回所有会话
   - 没有按用户查询会话的方法
   - 缺少用户级别的统计

## 改进方案

### 1. 数据库表结构升级

#### 方案 A：添加 user_id 字段到 sessions 表（推荐）

```sql
-- 迁移步骤 1: 添加 user_id 列
ALTER TABLE sessions ADD COLUMN user_id TEXT;

-- 迁移步骤 2: 创建索引
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at DESC);

-- 迁移步骤 3: 为现有数据设置默认用户（可选）
UPDATE sessions SET user_id = 'default' WHERE user_id IS NULL;

-- 迁移步骤 4: 添加外键约束（如果需要与用户系统集成）
-- ALTER TABLE sessions ADD CONSTRAINT fk_sessions_user
--     FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```

**优点**：
- 简单直接
- 保持表结构简单
- 易于查询和管理

**缺点**：
- 需要数据迁移
- 如果会话很多，迁移可能耗时

#### 方案 B：创建新的 user_sessions 表

```sql
-- 新表结构
CREATE TABLE user_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_user_sessions_user ON user_sessions(user_id, updated_at DESC);

-- 迁移旧数据
INSERT INTO user_sessions (id, state, created_at, updated_at)
SELECT id, state, created_at, updated_at FROM sessions;

-- 重命名表
ALTER TABLE sessions RENAME TO sessions_old;
ALTER TABLE user_sessions RENAME TO sessions;
```

**优点**：
- 不需要修改现有表
- 可以并行运行迁移
- 可以回滚

**缺点**：
- 表结构更复杂
- 占用更多存储空间

### 2. 接口改进

#### DatabaseProtocol 协议扩展

```python
from typing import Optional, Dict, Any, List

class DatabaseProtocol(Protocol):
    """数据库协议 - 扩展支持多用户"""

    # ===== 现有接口（保持兼容）=====
    async def save_state(self, session_id: str, state: Dict[str, Any]) -> bool: ...
    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    async def delete_state(self, session_id: str) -> bool: ...

    # ===== 新增多用户接口 =====

    async def save_state_for_user(
        self,
        user_id: str,
        session_id: str,
        state: Dict[str, Any]
    ) -> bool:
        """为指定用户保存会话状态"""
        ...

    async def load_state_for_user(
        self,
        user_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """加载指定用户的会话状态"""
        ...

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话（向后兼容）"""
        ...

    async def list_sessions_for_user(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """列出指定用户的会话"""
        ...

    async def delete_user_sessions(self, user_id: str) -> int:
        """删除指定用户的所有会话"""
        ...

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户统计信息"""
        ...

    # 其他接口保持不变
    async def save_event(self, session_id: str, event: Dict[str, Any]) -> bool: ...
    async def load_events(self, session_id: str, limit: Optional[int] = None, since: Optional[str] = None) -> List[Dict[str, Any]]: ...
    # ... 其他方法
```

### 3. AsyncDatabaseManager 实现

```python
class AsyncDatabaseManager:
    """异步数据库管理器 - 支持多用户"""

    async def initialize(self):
        """初始化数据库表结构（带迁移）"""
        if self._initialized:
            return

        async with self._transaction() as conn:
            # 检查 user_id 列是否存在
            cursor = await conn.execute(
                "PRAGMA table_info(sessions)"
            )
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'user_id' not in column_names:
                # 执行迁移：添加 user_id 列
                logger.info("Migrating database: adding user_id column to sessions")
                await conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sessions_user "
                    "ON sessions(user_id, updated_at DESC)"
                )
                # 为现有数据设置默认用户
                await conn.execute(
                    "UPDATE sessions SET user_id = 'default' WHERE user_id IS NULL"
                )
                logger.info("Database migration completed")

        # 其他表初始化保持不变
        # ...

    async def save_state_for_user(
        self,
        user_id: str,
        session_id: str,
        state: Dict[str, Any]
    ) -> bool:
        """为指定用户保存会话状态"""
        try:
            state['user_id'] = user_id
            state['updated_at'] = datetime.now().timestamp()
            state['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            state_json = json.dumps(state, ensure_ascii=False)

            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO sessions (id, user_id, state, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, user_id, state_json, state['last_active'])
                )
            logger.debug(f"Saved state for user {user_id}, session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save state failed: {e}")
            return False

    async def list_sessions_for_user(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """列出指定用户的会话"""
        try:
            query = "SELECT state FROM sessions WHERE user_id = ? ORDER BY updated_at DESC"
            params = [user_id]

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            async with self._transaction() as conn:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()

                sessions = []
                for row in rows:
                    try:
                        data = json.loads(row[0])
                        sessions.append({
                            "id": data.get("session_id"),
                            "user_id": data.get("user_id"),
                            "title": data.get("title", "New Chat"),
                            "updated_at": data.get("updated_at", 0)
                        })
                    except Exception:
                        continue

                return sessions
        except Exception as e:
            logger.error(f"List sessions for user {user_id} failed: {e}")
            return []

    async def delete_user_sessions(self, user_id: str) -> int:
        """删除指定用户的所有会话"""
        try:
            async with self._transaction() as conn:
                # 获取要删除的会话 ID
                cursor = await conn.execute(
                    "SELECT id FROM sessions WHERE user_id = ?",
                    (user_id,)
                )
                session_ids = [row[0] for row in await cursor.fetchall()]

                # 删除会话
                if session_ids:
                    placeholders = ','.join('?' * len(session_ids))
                    await conn.execute(
                        f"DELETE FROM sessions WHERE user_id = ? AND id IN ({placeholders})",
                        [user_id] + session_ids
                    )

                # 级联删除事件
                await conn.execute("DELETE FROM events WHERE session_id IN (?)", session_ids)

            logger.info(f"Deleted {len(session_ids)} sessions for user {user_id}")
            return len(session_ids)
        except Exception as e:
            logger.error(f"Delete user sessions failed: {e}")
            return 0

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户统计信息"""
        try:
            async with self._transaction() as conn:
                # 会话统计
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = ?",
                    (user_id,)
                )
                session_count = (await cursor.fetchone())[0]

                # 事件统计
                cursor = await conn.execute("""
                    SELECT COUNT(*)
                    FROM events e
                    JOIN sessions s ON e.session_id = s.id
                    WHERE s.user_id = ?
                """, (user_id,))
                event_count = (await cursor.fetchone())[0]

                # 记忆统计
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE user_id = ?",
                    (user_id,)
                )
                memory_count = (await cursor.fetchone())[0]

                return {
                    "user_id": user_id,
                    "sessions": session_count,
                    "events": event_count,
                    "memories": memory_count
                }
        except Exception as e:
            logger.error(f"Get user stats failed: {e}")
            return {}
```

### 4. AgentState 模型改进

```python
class AgentState(BaseModel):
    """Agent state model - 扩展支持用户信息"""

    session_id: str
    user_id: Optional[str] = None  # 新增：用户 ID
    status: AgentStatus = AgentStatus.IDLE
    history: List[Dict] = []
    active_skill: Optional[str] = None
    intent_session: Dict[str, Any] = Field(default_factory=dict)
    current_plan: List[str] = []
    pending_tool_call: Optional[Dict] = None
    title: str = "New Chat"
    shared_memory: Dict[str, Any] = {}
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
```

### 5. 使用示例

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
    user_id=user_id,  # 设置用户 ID
    title="我的对话"
)
await db.save_state_for_user(user_id, session_id, state.model_dump())

# 列出用户的所有会话
user_sessions = await db.list_sessions_for_user(user_id)
print(f"用户 {user_id} 有 {len(user_sessions)} 个会话")

# 获取用户统计
stats = await db.get_user_stats(user_id)
print(f"用户统计: {stats}")

# 删除用户的所有会话
deleted_count = await db.delete_user_sessions(user_id)
print(f"删除了 {deleted_count} 个会话")
```

## 向后兼容性

### 保持现有接口

```python
# 现有代码仍然可用
await db.save_state(session_id, state)
await db.load_state(session_id)
await db.list_sessions()
```

### 迁移策略

1. **阶段 1：添加 user_id 列**
   - 使用 ALTER TABLE 添加列
   - 为现有数据设置默认值

2. **阶段 2：更新接口**
   - 保持现有接口
   - 添加新的多用户接口

3. **阶段 3：逐步迁移代码**
   - 新代码使用多用户接口
   - 旧代码继续使用现有接口

4. **阶段 4：废弃旧接口（可选）**
   - 标记为 deprecated
   - 计划未来版本移除

## 迁移脚本

```python
# migrate_add_user_id.py
import asyncio
from assistant.db import AsyncDatabaseManager

async def migrate():
    """数据库迁移：添加 user_id 列"""
    db = AsyncDatabaseManager("museum_assistant.db")

    # 检查是否需要迁移
    await db.initialize()

    print("Migration completed!")

if __name__ == "__main__":
    asyncio.run(migrate())
```

## 总结

### 改进内容

1. ✅ 添加 user_id 到 sessions 表
2. ✅ 创建用户索引提高查询性能
3. ✅ 扩展 DatabaseProtocol 协议
4. ✅ 实现多用户查询接口
5. ✅ 保持向后兼容性

### 新增功能

- 按用户列出会话
- 用户统计信息
- 批量删除用户会话
- 用户权限验证

### 性能优化

- user_id 索引加速用户查询
- 支持分页查询
- 减少不必要的数据加载
