# Goose 源码研读与 Rust 进阶学习计划

**目标**：通过剖析 Goose (AI Agent) 源码，掌握 Rust 核心编程思想，理解 AGI Agent 的架构设计（基于 MCP 协议与状态机）。

## 阶段一：全貌与骨架 (Project Structure & Workspace)
**重点**：理解 Rust 的工程化组织方式。
**Rust 知识点**：`Cargo Workspace`, `Crates`, `Modules`, `Toml` 配置。

- [ ] **1.1 解析 `Cargo.toml` (Root)**
    - 目标：了解这是一个 Workspace 项目。查看 `[workspace]` 成员列表，理清 `goose` (核心库), `goose-cli` (入口), `goose-mcp` (协议层) 的依赖关系。
    - 思考：为什么大型 Rust 项目要拆分 Crates？

- [ ] **1.2 寻找入口 `goose-cli`**
    - 文件：`crates/goose-cli/src/main.rs`
    - 目标：追踪程序启动流程。如何解析命令行参数？如何初始化 Log？
    - Rust 关键：`clap` (命令行解析库), `Result<?>` (错误处理传播), `env_logger`。

---

## 阶段二：大脑与记忆 (Core Logic & State Management)
**重点**：理解 Agent 如何维护上下文和对话历史。这是 Rust "所有权"机制发挥作用的地方。
**Rust 知识点**：`Struct`, `Enum`, `Ownership`, `Lifetimes`, `Vec`.

- [ ] **2.1 会话定义 `Session`**
    - 目录：`crates/goose/src/session/` (或类似 core 目录)
    - 目标：找到 `struct Session`。它是如何存储 `Message` 的？
    - 思考：Goose 如何保证消息历史在多轮对话中不丢失、不产生内存泄漏？

- [ ] **2.2 消息类型 `Message` & `Role`**
    - 目标：分析消息模型。
    - Rust 关键：`Enum` (枚举) 的强大之处。Rust 的枚举不仅仅是常量，可以携带数据（Algebraic Data Types）。
    - *代码关注点*：看它是如何用 Enum 区分 `User`, `Assistant`, `ToolResult` 的。

---

## 阶段三：神经系统 (The Loop & Asynchronous)
**重点**：Agent 的核心循环（思考 -> 行动 -> 观察）。理解 Rust 的异步运行时。
**Rust 知识点**：`Async/Await`, `Tokio`, `Pattern Matching` (match).

- [ ] **3.1 主循环 `run_loop` / `step`**
    - 目标：找到驱动 Agent 运转的 `while` 循环。
    - 逻辑：发送 Prompt -> 等待 LLM -> 匹配返回结果 -> (如果是工具调用) -> 执行 -> 循环。
    - Rust 关键：`match` 模式匹配（Rust 的杀手锏），如何优雅地处理 LLM 的各种返回状态。

- [ ] **3.2 异步运行时**
    - 目标：理解为什么几乎所有函数都带 `async`。
    - 思考：在等待 OpenAI 回复时，Rust 是如何不阻塞线程的？(Tokio Runtime)。

---

## 阶段四：感官与表达 (Traits & Abstraction)
**重点**：如何兼容不同的 LLM（OpenAI, Anthropic, Ollama）。
**Rust 知识点**：`Traits` (特质), `Generics` (泛型), `Box<dyn Trait>` (动态分发).

- [ ] **4.1 Provider 抽象**
    - 目录：`crates/goose/src/providers/`
    - 目标：找到 `trait LLMProvider` (或类似命名)。
    - 代码赏析：看 Rust 如何通过 Trait 定义统一的接口（Interface），实现“策略模式”。

- [ ] **4.2 配置管理**
    - 目标：查看如何从配置文件加载 API Key 和模型参数。
    - Rust 关键：`Serde` (序列化/反序列化库)，这是 Rust 处理 JSON/YAML 的标准。

---

## 阶段五：手脚与工具 (MCP & Tooling)
**重点**：Model Context Protocol 的实现，以及 Rust 的安全性。
**Rust 知识点**：`Error Handling`, `JSON-RPC`, `FileSystem I/O`.

- [ ] **5.1 MCP 协议实现**
    - Crate：`goose-mcp`
    - 目标：理解 Goose 如何向 LLM 描述工具（Function Calling Schema），以及如何解析 LLM 的工具调用请求。

- [ ] **5.2 执行环境**
    - 目标：查看 Goose 如何执行 Shell 命令或读写文件。
    - 思考：Rust 的类型安全如何防止 Agent 产生意外的破坏性操作？

---

## 阶段六：实战演练 (Contribution / Modification)
**目标**：修改代码，验证学习成果。

- [ ] **6.1 Hello World 修改**：修改 CLI 启动时的欢迎语。
- [ ] **6.2 增加一个简单的内置工具**：例如添加一个 `get_current_time` 的工具函数。
- [ ] **6.3 编译与运行**：使用 `cargo run` 调试你的修改。
