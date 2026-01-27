# Goose-rs 实现文档（阶段 D 数据库设计要点与演进）

阶段 D 的目标：落地正式的数据库数据字典与逐版本迁移方案，确保现有数据的平滑演进、向后兼容性，以及未来字段扩展的可控性。

1) 数据字典总览
- 表：sessions
- 表：messages
- 其他表：如需支持附件、资源等，将在阶段后续补充。

2) 现有设计的阶段性迁移点（版本化）
- v1：创建 schema_version 表，记录已应用的数据库版本
- v2：新增 sessions.user_recipe_values_json 字段
- v3：新增 messages.metadata_json 字段
- v4：新增 sessions.name、sessions.user_set_name 字段
- v5：新增 sessions.session_type 字段，并创建索引 idx_sessions_type
- v6：新增 sessions.provider_name、sessions.model_config_json 字段

3) 具体数据字典（字段、类型、约束、索引）
- 表：sessions
  - id: TEXT PRIMARY KEY
  - name: TEXT
  - description: TEXT
  - user_set_name: BOOLEAN
  - session_type: TEXT NOT NULL DEFAULT 'user'
  - working_dir: TEXT
  - created_at: TIMESTAMP
  - updated_at: TIMESTAMP
  - extension_data: TEXT
  - total_tokens: INTEGER
  - input_tokens: INTEGER
  - output_tokens: INTEGER
  - accumulated_total_tokens: INTEGER
  - accumulated_input_tokens: INTEGER
  - accumulated_output_tokens: INTEGER
  - schedule_id: TEXT
  - recipe_json: TEXT
  - user_recipe_values_json: TEXT
  - provider_name: TEXT
  - model_config_json: TEXT
  - Indexes: idx_sessions_type (session_type)
- 表：messages
  - id: INTEGER PRIMARY KEY AUTOINCREMENT
  - session_id: TEXT NOT NULL REFERENCES sessions(id)
  - role: TEXT NOT NULL
  - content_json: TEXT NOT NULL
  - created_timestamp: INTEGER NOT NULL
  - timestamp: TIMESTAMP
  - tokens: INTEGER
  - metadata_json: TEXT
  - Indexes: idx_messages_session (session_id), idx_messages_timestamp (timestamp)

4) 迁移 SQL 实现要点
- v1: 建表 schema_version
  - CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
- v2: 增加 sessions.user_recipe_values_json
  - ALTER TABLE sessions ADD COLUMN user_recipe_values_json TEXT;
- v3: 增加 messages.metadata_json
  - ALTER TABLE messages ADD COLUMN metadata_json TEXT;
- v4: 增加 sessions.name、sessions.user_set_name
  - ALTER TABLE sessions ADD COLUMN name TEXT;
  - ALTER TABLE sessions ADD COLUMN user_set_name BOOLEAN;
- v5: 增加 sessions.session_type 并创建索引
  - ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'user';
  - CREATE INDEX idx_sessions_type ON sessions(session_type);
- v6: 增加 sessions.provider_name、sessions.model_config_json
  - ALTER TABLE sessions ADD COLUMN provider_name TEXT;
  - ALTER TABLE sessions ADD COLUMN model_config_json TEXT;

5) 持久化实现要点（阶段 D 的落地要点）
- 事务化写入与模式变更：迁移完成后，现有写入/读取路径需保持原子性和稳定性
- 数据迁移的幂等性：迁移脚本应具幂等性，避免重复应用
- 序列化策略：content_json、metadata_json 的 JSON 序列化/反序列化保持向前兼容

6) 验证与回滚
- 验证：在迁移完成后执行数据完整性检查、字段存在性检查、约束/索引可用性检查
- 回滚：如果需要回滚版本，应提供对应的回滚 SQL，确保数据不丢失

7) 与阶段 B/A 的对齐与依赖
- 阶段 D 的设计需严格对齐阶段 B 的字段命名与数据类型约定，确保后续合并无缝
- 阶段 F 将 Stage A/B/C/D 的设计综合为最终的实现文档

8) 下一步计划
- 完成阶段 D 的迁移 SQL 与数据字典落地后，进入阶段 E 的运行与测试设计，并在阶段 F 做最终文档合并。 
