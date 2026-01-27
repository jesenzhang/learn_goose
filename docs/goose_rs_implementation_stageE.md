# Goose-rs Stage E: Run & Test Plan

日期：YYYY-MM-DD

1) 目标
- 为 goose-rs 提供可执行的测试策略，覆盖持久化路径（写入/读取/替换）、事务性、幂等性以及 JSON 序列化的一致性，确保迁移与未来字段扩展的可验证性。

2) 测试范围
- 覆盖 goose/crates/goose 相关的会话与消息持久化实现（session_manager.rs、session_storage.rs、conversation/message.rs 等）。
- 包含数据字典字段的序列化与反序列化测试的边界。
- 覆盖并发写入的基本场景与错误处理路径。

3) 测试类型与用例（草案）
- 单元测试（Unit）
  - MessageMetadata 的默认值与可见性方法的正确性
  - MessageContent 的序列化/反序列化一致性
  - ProviderMetadata 的 serde 序列化行为
- 集成测试（Integration）
  - SessionStorage 的 create_schema、run_migrations 是否正确执行
  - add_message 的持久化写入是否正确，且更新 sessions.updated_at
  - get_conversation 的读取与反序列化是否正确
  - replace_conversation 的替换逻辑是否覆盖原有消息
  - 导出/导入会话的端到端流程（如果在阶段 F 时落地）
- 并发测试（Concurrency）
  - 多个任务同时创建会话并写入消息，观察数据一致性与唯一性
- 边界测试（Boundary）
  - 空内容、空消息集合、极端时间戳的处理

4) 测试实现要点（实现建议）
- 测试用例的环境准备
  - 使用临时目录作为 data_dir，创建 sessions.db 的 sqlite 数据库
  - 在测试中启用 SQLite WAL 模式以提升并发写入能力
- 数据准备与清理
  - 每个测试结束应清理临时数据库，避免测试间数据污染
- 断言设计
  - 对消息的 content_json/metadata_json 的反序列化后的结构进行断言
  - 对会话中的消息数量、顺序、角色、以及创造时间点进行断言

5) 示例测试骨架（可直接作为起点）
- 单元测试示例：MessageMetadata 默认值
```rust
# [test]
fn test_message_metadata_default() {
    let m = crate::conversation::message::Message::user().with_text("hi");
    assert!(m.metadata.user_visible);
    assert!(m.metadata.agent_visible);
}
```
- 集成测试示例：写入并读取对话历史
```rust
# [tokio::test]
async fn test_session_write_read_conversation() {
    use std::path::PathBuf;
    let tmp_dir = tempfile::tempdir().unwrap();
    let data_dir = tmp_dir.path().to_path_buf();
    // 注意：这里给出示例，具体初始化需结合实际代码的构造方式
    // let storage = goose::session::SessionStorage::new(data_dir.clone());
    // 创建会话并写入消息
}
```

6) 运行测试的命令（示例）
- cargo test
- 或在 goose crate 级别执行：cargo test -p goose
- 如需并发测试，可设置 RUST_LOG=info 以观察日志输出

7) 依赖与环境
- Rust 工具链（cargo/rustc）应已安装
- sqlite3 运行时依赖（tests 使用）
- 需要 tempfile、tempdir 等用于创建临时目录的测试工具

8) 验收标准
- 所有阶段 E 的核心持久化行为在 Stage F 的最终合并中被覆盖

9) 与阶段 F 的衔接
- 将 Stage D 的迁移设计与 Stage E 的测试计划纳入最终合并，形成 docs/goose_rs_implementation.md 的完整版本
