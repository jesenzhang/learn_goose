# Goose-rs 实现文档（阶段 C：持久化实现与访问路径）

阶段 C 目标：对阶段 B 的字段对齐进行细化，明确写入/读取/替换等核心持久化路径，以及事务边界、幂等性设计，并提供代码位置引用。

1) 参考的核心实现点（代码引用）
- 写入消息：goose/crates/goose/src/session/session_manager.rs
- 相关实现：add_message(&self, session_id: &str, message: &Message) -> Result<()>
- 关键 SQL：INSERT INTO messages (session_id, role, content_json, created_timestamp, metadata_json) VALUES (?, ?, ?, ?, ?)
- 更新会话：UPDATE sessions SET updated_at = datetime('now') WHERE id = ?
- 读取对话：goose/crates/goose/src/session/session_manager.rs
- 读取 SQL：SELECT role, content_json, created_timestamp, metadata_json FROM messages WHERE session_id = ? ORDER BY timestamp
- 反序列化：content_json → Vec<MessageContent>，metadata_json → MessageMetadata
- 替换对话：replace_conversation 内部实现，先 DELETE FROM messages，然后 INSERT 新对话消息

2) 数据模型对齐（阶段 B 继续沿用）
- Message
  - id: Option<String>
  - role: Role
  - created: i64
  - content: Vec<MessageContent>
  - metadata: MessageMetadata
- MessageMetadata
  - user_visible: bool
  - agent_visible: bool
- MessageContent 枚举及子结构（TextContent、ImageContent、ToolRequest、ToolResponse、FrontendToolRequest、Thinking、RedactedThinking、SystemNotification 等）
- ProviderMetadata: serde_json::Map<String, serde_json::Value>

3) 数据库结构要点（阶段 B 草拟，阶段 D 完整化）
- messages 表：id, session_id, role, content_json, created_timestamp, timestamp, tokens, metadata_json
- sessions 表：id, name, description, user_set_name, session_type, working_dir, created_at, updated_at, extension_data, total_tokens, input_tokens, output_tokens, accumulated_total_tokens, accumulated_input_tokens, accumulated_output_tokens, schedule_id, recipe_json, user_recipe_values_json, provider_name, model_config_json
- content_json/metadata_json：JSON 序列化字段

4) 迁移与演进点
- v1: 创建 schema_version 表
- v2: 新增 sessions.user_recipe_values_json
- v3: 新增 messages.metadata_json
- v4: 新增 sessions.name、sessions.user_set_name
- v5: 新增 sessions.session_type，并创建 idx_sessions_type 索引
- v6: 新增 sessions.provider_name、sessions.model_config_json

5) 持久化实现要点（阶段 C 的要点）
- 事务边界：写入与更新在同一事务中完成
- 幂等性与幂等键设计：替换对话时确保一次性写入结果
- JSON 序列化策略：content_json、metadata_json 采用 serde_json

6) 验证与测试建议
- 针对阶段 C 的持久化路径：单笔写入、读取、替换、并发写入边界等测试

7) 数据字段的精确对齐（待阶段 D 完整化前的参考）
- Message
  - id: Option<String>
  - role: Role
  - created: i64
  - content: Vec<MessageContent>
  - metadata: MessageMetadata
- MessageMetadata
  - user_visible: bool
  - agent_visible: bool
- MessageContent 枚举及子结构
  - Text(TextContent)  // 字段：text: String
  - Image(ImageContent) // 字段：data: String, mime_type: String
  - ToolRequest { id, tool_call, metadata, tool_meta }
  - ToolResponse { id, tool_result, metadata }
  - ToolConfirmationRequest { id, tool_name, arguments, prompt }
  - ActionRequired { data }
  - FrontendToolRequest { id, tool_call }
  - ThinkingContent { thinking, signature }
  - RedactedThinkingContent { data }
  - SystemNotification { notification_type, msg }
- 系统工具/元数据
  - ProviderMetadata = serde_json::Map<String, serde_json::Value>
- content_json/metadata_json：JSON 序列化字段的准则
- 其他字段：如 created_timestamp 应存储为 INTEGER/INT64，表示消息创建时间

8) 下一步计划
- 在阶段 D 进行完全字段名与表约束的落地；阶段 E、F 继续实现路径细化与合并工作
