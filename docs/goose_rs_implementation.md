# Goose-rs 实现文档（阶段 A–F 最终合并版）

本文档综合了 goose-rs 项目的完整实现细节，涵盖架构总览、模块职责、数据模型、持久化设计、消息保存与读取实现、迁移策略、测试与部署等关键方面。

## 1. 概要与范围

### 1.1 目标与范围

本文档提供 goose-rs 项目的完整实现说明，重点覆盖：

- 架构总览与模块职责
- 数据模型与字段定义
- 数据库设计与迁移策略
- 消息保存与读取的实现细节
- 运行、测试与部署

### 1.2 工作区与模块结构

goose-rs 是一个 Rust 工作区，包含以下核心 crates：

- **goosecrates/goose/****
  - 核心库，包含所有关键的数据结构、持久化实现和业务逻辑
  - 核心 src 目录：
    - `conversation/` - 消息、对话相关实现
    - `session/` - 会话管理与持久化
    - `providers/` - LLM 提供者实现
    - `model.rs` - 模型配置
    - 其他工具与辅助模块

- **goose-servercrates/goose-server/****
  - HTTP 服务端实现

- **goose-cli**crates/goose-cli/****
  - 命令行接口

- **goose-mcp**crates/goose-mcp/****
  - MCP 协议实现

- **goose-acp**crates/goose-acp/****
  - Anthropic Compatible Provider 实现

- **goose-bench**crates/goose-bench/****
  - 性能测试

- **goose-test**crates/goose-test/****
  - 测试工具

### 1.3 数据持久化核心组件

- 数据库位置：`sessions/sessions.db` (SQLite)
- 核心模块：`SessionManager`, `SessionStorage`
- 会话存储位置：`Paths::data_dir() / sessions`

## 2. 数据模型总览

### 2.1 核心数据结构

#### Message 结构

```rust
pub struct Message {
    pub id: Option<String>,
    pub role: Role,
    pub created: i64,
    pub content: Vec<MessageContent>,
    pub metadata: MessageMetadata,
}
```

**字段说明：**
- `id`: 可选的消息唯一标识符
- `role`: 消息角色 (User/Assistant)
- `created`: 创建时间戳
- `content`: 消息内容数组，支持多种内容类型
- `metadata`: 消息可见性元数据

#### MessageMetadata 结构

```rust
pub struct MessageMetadata {
    pub user_visible: bool,   // 是否在 UI 中对用户可见
    pub agent_visible: bool,  // 是否在 LLM 上下文窗口中可见
}
```

#### MessageContent 枚举

```rust
pub enum MessageContent {
    Text(TextContent),
    Image(ImageContent),
    ToolRequest(ToolRequest),
    ToolResponse(ToolResponse),
    ToolConfirmationRequest(ToolConfirmationRequest),
    ActionRequired(ActionRequired),
    FrontendToolRequest(FrontendToolRequest),
    Thinking(ThinkingContent),
    RedactedThinking(RedactedThinkingContent),
    SystemNotification(SystemNotificationContent),
}
```

### 2.2 辅助数据结构

- `ToolRequest`: 工具调用请求
- `ToolResponse`: 工具调用响应
- `ActionRequired`: 需要用户操作的数据
- `ThinkingContent`: 思考内容
- `ProviderMetadata`: 提供者特定的元数据

### 2.3 Conversation 结构

```rust
pub struct Conversation(Vec<Message>);
```

Conversation 是 `Vec<Message>` 的简单封装，表示消息序列。

## 3. 数据库设计与迁移

### 3.1 数据库方案

- **数据库类型**: SQLite
- **连接池**: 使用 `sqlx` 的 SQLite 连接池
- **文件位置**: `sessions/sessions.db`
- **日志模式**: WAL (Write-Ahead Logging) 用于提升并发性能

### 3.2 数据表结构

#### sessions 表

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    user_set_name BOOLEAN DEFAULT FALSE,
    session_type TEXT NOT NULL DEFAULT 'user',
    working_dir TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extension_data TEXT DEFAULT '{}',
    total_tokens INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    accumulated_total_tokens INTEGER,
    accumulated_input_tokens INTEGER,
    accumulated_output_tokens INTEGER,
    schedule_id TEXT,
    recipe_json TEXT,
    user_recipe_values_json TEXT,
    provider_name TEXT,
    model_config_json TEXT
);
```

#### messages 表

```sql

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_timestamp INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tokens INTEGER,
    metadata_json TEXT
);
```

#### 索引

```sql
CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX idx_sessions_type ON sessions(session_type);
```

### 3.3 迁移策略

当前 schema 版本：`CURRENT_SCHEMA_VERSION = 6`

迁移版本说明：

- **v1**: 创建 `schema_version` 表
- **v2**: 新增 `sessions.user_recipe_values_json` 字段
- **v3**: 新增 `messages.metadata_json` 字段
- **v4**: 新增 `sessions.name` 和 `sessions.user_set_name` 字段
- **v5**: 新增 `sessions.session_type` 字段并创建 `idx_sessions_type` 索引
- **v6**: 新增 `sessions.provider_name` 和 `sessions.model_config_json` 字段

## 4. 消息保存与读取实现

### 4.1 持久化入口

**SessionManager API** (crates/goose/src/session/session_manager.rs)

- `create_session(working_dir, name, session_type) -> Result<Session>`
- `add_message(session_id, message) -> Result<()>`
- `get_session(id, include_messages) -> Result<Session>`
- `replace_conversation(id, conversation) -> Result<()>`
- `list_sessions() -> Result<Vec<Session>>`
- `delete_session(id) -> Result<()>`

### 4.2 消息保存流程

**路径**: `SessionManager::add_message` → `SessionStorage::add_message`

实现步骤：

1. 开始事务 `pool.begin().await?`
2. 序列化元数据 `serde_json::to_string(&message.metadata)`
3. 插入消息到数据库：
   ```sql
   INSERT INTO messages (session_id, role, content_json, created_timestamp, metadata_json)
   VALUES (?, ?, ?, ?, ?)
   ```
4. 更新会话时间戳：
   ```sql
   UPDATE sessions SET updated_at = datetime('now') WHERE id = ?
   ```
5. 提交事务 `tx.commit().await?`

### 4.3 消息读取流程

**路径**: `SessionManager::get_session` → `SessionStorage::get_conversation`

实现步骤：

1. 查询消息：
   ```sql
   SELECT role, content_json, created_timestamp, metadata_json
   FROM messages
   WHERE session_id = ?
   ORDER BY timestamp
   ```
2. 反序列化 `content_json` → `Vec<MessageContent>`
3. 反序列化 `metadata_json` → `MessageMetadata`
4. 构造 `Message` 对象和 `Conversation` 结构

### 4.4 对话替换流程

**路径**: `SessionManager::replace_conversation` → `SessionStorage::replace_conversation_inner`

实现步骤：

1. 开始事务
2. 删除旧消息：
   ```sql
   DELETE FROM messages WHERE session_id = ?
   ```
3. 插入新对话的所有消息
4. 提交事务

### 4.5 事务边界

所有写入操作（add_message、replace_conversation）都：
- 在单个事务中执行
- 使用 WAL 模式支持并发
- 失败时自动回滚

### 4.6 JSON 序列化策略

- **content_json**: 存储序列化后的 `Vec<MessageContent>`
- **metadata_json**: 存储序列化后的 `MessageMetadata`
`serde_json::to_string()` 用于序列化
`serde_json::from_str()` 用于反序列化

## 5. 运行与测试

### 5.1 构建与运行

```bash
# 构建
cd goose-rs
cargo build

# 运行测试
cargo test

# 运行 goose-rs 服务
cargo run -p goose-server
```

### 5.2 测试覆盖点

建议的测试场景：

- 单元测试：
  - `MessageMetadata` 的默认值和可见性方法
  - `MessageContent` 的序列化/反序列化
- `ProviderMetadata` 的序列化

- 集成测试：
  - 会话创建与消息写入的端到端流程
  - 对话替换的正确性
  - 迁移脚本的正确执行

- 并发测试：
  - 多个任务同时写入同一会话的消息
  - 验证数据一致性和唯一性

## 6. 迁移与演进策略

### 6.1 迁移执行

- 初始化时检查 `schema_version` 表
- 按版本号顺序应用迁移
- 每个迁移步骤记录到 `schema_version` 表

### 6.2 版本兼容性

- 新字段使用 `ALTER TABLE` 添加，确保向后兼容
- JSON 字段的变更通过序列化/反序列化保持兼容

### 6.3 回滚策略

- 每个迁移版本应有对应的回滚步骤
- 建议在应用新迁移前备份数据库

## 7. 数据字典

### 7.1 sessions 表字段映射

| 数据库列 | Rust 类型 | 可空 | 默认值 | 说明 |
|----------|----------|------|--------|------|
| id | String | false | - | 会话唯一标识符 |
| name | String | false | - | 会话名称 |
| description | String | false | - | 会话描述 |
| user_set_name | bool | false | FALSE | 用户是否设置了名称 |
| session_type | String | false | 'user' | 会话类型 |
| working_dir | String | false | - | 工作目录路径 |
| created_at | DateTime<Utc> | true | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DateTime<Utc> | true | CURRENT_TIMESTAMP | 更新时间 |
| extension_data | String | false | '{}' | 扩展数据 (JSON) |
| total_tokens | i32 | true | - | Token 总数 |
| input_tokens | i32 | true | - | 输入 Token 数 |
| output_tokens | i32 | true | - | 输出 Token 数 |
| accumulated_total_tokens | i32 | true | - - | 累计 Token 总数 |
| accumulated_input_tokens | i32 | true | - | 累计输入 Token 数 |
| accumulated_output_tokens | i32 | true | - | 累计输出 Token 数 |
| schedule_id | String | true | - | 关联的定时任务 ID |
| recipe_json | String | true | - | Recipe 配置 (JSON) |
| user_recipe_values_json | String | true | - | 用户提供的 Recipe 值 配置 (JSON) |
| provider_name | String | true | - - | LLM 提供者名称 |
| model_config_json | String | true | - | 模型配置 (JSON) |

### 7.2 messages 表字段映射

| 数据库列 | Rust 类型 | 可空 | 默认值 | 说明 |
|----------|----------|------|--------|------|
| id | i64 | false | - AUTOINCREMENT | 消息自增 ID |
| session_id | String | false | - | 关联的会话 ID |
| role | String | false | - | 消息角色 |
| content_json | String | false | - | 消息内容 (JSON) |
| created_timestamp | i64 | false | - | 创建时间戳 |
| timestamp | DateTime | true | CURRENT_TIMESTAMP | 时间戳 |
| tokens | i32 | true | - | | Token 数 |
| metadata_json | String | true | - | | 消息元数据 (JSON) |

### 7.3 schema_version 表字段映射

| 数据库列 | Rust 类型 | 可空 | 默认值 | 说明 |
|----------|----------|------|--------|------|
| version | i32 | false | - | Schema 版本号 |
| applied_at | DateTime<Utc> | true | CURRENT_TIMESTAMP | 应用时间 |

### 7.4 Rust 类型 ↔ SQLite 类型映射

| Rust 类型 | SQLite 类型 | 说明 |
|----------|------------|------|
| String | TEXT | 字符串 |
| i64 | INTEGER | 64 位整数 |
| i32 | INTEGER | 32 位整数 |
| bool | BOOLEAN | 布尔值 (0/1) |
| DateTime<Utc> | TIMESTAMP | 时间戳 |
| Vec<T> (JSON) | TEXT | 数组序列化为 JSON 文本 |
| Option | - | NULLABLE | 可空字段 |

## 8. 代码位置索引

### 8.1 核心实现文件

- `crates/goose/src/lib.rs` - 核心库入口
- `crates/goose/src/conversation/mod.rs` - 对话结构
- `crates/goose/src/conversation/message.rs` - 消息模型定义
- `crates/goose/src/session/session_manager.rs` - 会话管理器
- `crates/goose/src/session/session_storage.rs` - 持久化存储
- `crates/goose/src/model.rs` - 模型配置
- `crates/goose/src/providers/` - LLM 提供者

### 8.2 相关实现文件

- `crates/goose-server/src/` - 服务端实现
- `crates/goose-cli/src/` - CLI 实现
- `crates/goose-mcp/src/` - MCP 协议
- `crates/goose-acp/src/` - ACP Provider

### 8.3 测试文件

- `crates/goose/tests/` - 集成测试
- `crates/goose/tests/agent.rs`
- `crates/goose/tests/mcp_integration_test.rs`

## 9. 阶段性设计考虑

### 9.1 性能优化

- 使用 SQLite WAL 模式提升并发性能
- 建立适当的索引：
  - `idx_messages_session` - 加速按会话查询
  - `idx_messages_timestamp` - 加速时间范围查询
  - `idx_sessions_updated` - 加速最近会话查询
  - `idx_sessions_type` - 支持按类型筛选

### 9.2 数据一致性

- 所有写入操作使用事务确保原子性
- 对话替换先删除后插入，避免数据不一致
- 使用时间戳 `created_timestamp` 作为消息排序依据

### 9.3 扩展性设计

- JSON 字段 (`content_json`, `metadata_json`, `extension_data` 等) 提供灵活的元数据存储
- 扩展新字段通过 ALTER TABLE 添加，保持向后兼容

### 9.4 安全考虑

- 对用户输入进行 Unicode 标签清理（`sanitize_unicode_tags`）
- 消息角色和会话类型的严格校验
- 文件路径和数据库访问的安全性控制

## 10. 变更日志

### 10.1 Schema 版本历史

- v1: 创建 schema_version 表
- v2: 新增 user_recipe_values_json
- v3: 新增 messages.metadata_json
- v4: 新增 name 和 user_set_name
- v5: 新增 session_type 和索引
- v6: 新增 provider_name 和 model_config_json

### 10.2 关键变更点

- v2: 引入用户提供的 Recipe 值支持
- v3: 引入消息元数据、支持可见性控制
- v4: 支持用户自定义会话名称
- v5: 支持多类型会话（User/Scheduled/SubAgent/Hidden/Terminal）
- v6: 支持多个 LLM 提供者和模型配置的持久化

## 11. 部署说明

### 11.1 数据目录结构

```
goose_data/
├─ sessions/
│   └── sessions.db
├─ (配置文件)
```

### 11.2 环境变量

- `GOOSE_DATA_DIR` - 数据目录路径
- 数据库连接参数通过 `SqliteConnectOptions` 配置
- WAL 模式和 busy_timeout 配置

---

**文档版本**: 1.0.0  
**最后更新**: 2026-01-27  
**维护者**: 文档生成团队
