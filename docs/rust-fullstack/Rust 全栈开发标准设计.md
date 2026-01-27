# **全栈开发标准：Rust 后端系统设计与 AI 驱动的闭环架构深度研究报告**

## **1\. 执行摘要与架构愿景：定义 2025 年的系统级后端标准**

在当代软件工程的演进脉络中，全栈开发的标准正经历一场深刻的范式转移。随着前端选型日益趋向于“类型安全”与“组件化”（如 React/Vue \+ TypeScript \+ Tailwind 的成熟体系），后端的角色已不再仅仅是数据存取的管道，而是演变为业务逻辑的严密守护者与类型定义的源头。本报告旨在确立一套 **Rust 后端系统设计标准**，其核心目标是与现代前端标准形成完美的“闭环”（Closed Loop），并通过引入“规范驱动开发”（Spec-Driven Development, SDD）的方法论，解决系统级编程语言在 AI 辅助开发时代的落地难题。

Rust 语言凭借其内存安全、零成本抽象及极其严格的类型系统，已成为构建高可靠性后端的首选 1。然而，Rust 的高学习曲线与编译器严格的借用检查（Borrow Checker）规则，长期以来构成了其在大规模业务开发中的门槛。本标准提出了一种全新的架构视角：**将 Rust 后端视为一个“无头核心”（Headless Core）**，通过严格的分层架构（Layered Architecture）和工作空间（Workspace）管理，实现业务逻辑与具体的接口层（Web、桌面 Tauri、命令行 CLI）解耦 2。

更为关键的是，本标准不仅是针对人类工程师的编码指南，更是一份面向 AI 智能体（如 Claude Code）的“技术宪法”。通过将架构约束、所有权模型及错误处理层级显式化为高密度的规范文档（spec.md），我们能够填补 AI 认知与 Rust 编译器之间的鸿沟，实现高质量代码的自动化生成，从而真正闭合全栈开发的效率环 4。

## ---

**2\. 认知鸿沟与代理式开发范式：AI 时代的 Rust 工程学**

从传统的辅助编码（Copilot 模式）向自主代理（Agentic 模式）的转变，要求后端架构必须具备极高的“上下文可解释性”。Rust 语言的特性——即在编译期强制执行内存安全——对 AI 代理提出了独特的挑战。LLM（大语言模型）本质上是基于概率的预测器，而 Rust 编译器则是基于规则的零容忍验证器。这种冲突导致了“上下文漂移”（Context Drift）现象：随着对话长度的增加，AI 容易遗忘复杂的生命周期约束或所有权规则，导致生成的代码陷入“编译-修复-再报错”的死循环 4。

### **2.1 上下文工程与“技术宪法”**

为了解决上述问题，本标准引入了\*\*上下文工程（Context Engineering）\*\*的概念。我们在项目根目录建立两级规范体系，作为 AI 的“认知锚点”（Cognitive Anchor）：

1. **全局宪法 (CLAUDE.md)**：这是项目的元配置文件，定义了不可动摇的全局规则。它包括构建命令（cargo build）、代码风格（rustfmt）、以及严禁使用的模式（如禁止在生产代码中使用 .unwrap()）。该文件被 AI 代理隐式加载，作为其决策的基准线 4。  
2. **局部法案 (spec.md)**：这是针对特定功能模块的动态执行指令。它详细描述了当前迭代的数据结构、接口签名（Trait Signatures）及业务流程。spec.md 充当了“单一事实来源”（Single Source of Truth, SSOT），消除了自然语言描述中的歧义，强制 AI 遵循预设的架构路径 4。

### **2.2 规范驱动开发 (SDD) 的生命周期**

本标准确立了基于 SDD 的开发流，包含五个核心阶段：

* **初始化 (Bootstrap)**：创建包含基础架构约束的规范模板。  
* **交互式细化 (Interview Mode)**：AI 阅读规范草案，向架构师提问以补全细节（如并发锁的选择）。  
* **规划 (Planning)**：AI 生成 plan.md，将复杂需求拆解为原子化的 Rust 实现步骤。  
* **实现 (Implementation)**：AI 执行代码生成，利用编译器的错误信息作为反馈循环进行自我修正。  
* **验证 (Verification)**：运行规范中定义的测试用例，确保逻辑正确性 4。

这种模式将开发者的角色从“代码编写者”转变为“规范撰写者”和“架构审核者”，利用 Rust 的类型系统作为 AI 生成代码的质量围栏，确保了全栈闭环中的后端既高效又安全。

## ---

**3\. 宏观架构设计：工作空间与无头核心**

为了实现全栈标准的闭环，后端架构必须具备极强的适应性，能够同时支撑 Web 前端、桌面应用（Tauri）以及命令行工具（CLI）。传统的单体应用结构已无法满足这种多端分发的需求。本标准强制采用 **Cargo Workspace（工作空间）** 结合 **六边形架构（Hexagonal Architecture）** 的模式 5。

### **3.1 单一仓库（Monorepo）的目录结构**

推荐的目录结构如下，旨在实现关注点分离（Separation of Concerns）：

project-root/

├── Cargo.toml \# 工作空间配置，定义 members 和 resolver \= "2"

├── CLAUDE.md \# AI 全局宪法

├── spec.md \# 当前功能的局部规范

├── Makefile / Justfile \# 自动化脚本

├── crates/

│ ├── core/ \# 【核心领域层】纯 Rust 代码，无 I/O，定义实体与接口

│ │ ├── src/

│ │ │ ├── models.rs \# 领域实体 (Structs, Enums)

│ │ │ ├── ports.rs \# 端口定义 (Traits: Repository, Service)

│ │ │ └── errors.rs \# 领域错误 (thiserror)

│ │ └── Cargo.toml

│ ├── infra/ \# 【基础设施层】适配器实现，包含数据库、外部 API 依赖

│ │ ├── src/

│ │ │ ├── persistence/\# SQLx Repository 实现

│ │ │ ├── auth/ \# JWT/Argon2 实现

│ │ │ └── external/ \# Reqwest 客户端

│ │ └── Cargo.toml

│ ├── api/ \# 【应用接入层】Axum Web 服务

│ │ ├── src/

│ │ │ ├── handlers/ \# HTTP 处理函数

│ │ │ ├── state.rs \# AppState 依赖注入

│ │ │ └── main.rs \# 二进制入口

│ │ └── Cargo.toml

│ ├── desktop/ \# 【桌面接入层】Tauri v2 应用

│ │ ├── src-tauri/ \# Rust 侧逻辑，调用 core 和 infra

│ │ └── Cargo.toml

│ └── shared/ \# 【全栈共享层】前后端通用的类型定义

│ ├── src/

│ │ └── dtos.rs \# 数据传输对象，派生 Specta/Serde

│ └── Cargo.toml

└── frontend/ \# 前端项目 (React/Vue \+ TypeScript)

### **3.2 “无头核心” (Headless Core) 理念**

在这一架构中，crates/core 是所谓的“无头核心”。它不依赖于任何具体的运行时框架（如 Axum 或 Tauri），也不包含数据库驱动（如 SQLx）的具体实现，仅定义特征（Traits） 2。

* **优势**：这种设计使得核心业务逻辑可以在 Web 服务器、桌面应用甚至 WASM 环境中复用。例如，一个“计算税费”的业务逻辑在 core 中定义后，既可以在服务器端被 Axum 调用以响应 API 请求，也可以被编译为 WASM 直接在前端浏览器中运行，实现极致的响应速度。  
* **AI 友好性**：对于 AI 代理而言，core 层是一个纯粹的逻辑沙箱。由于没有复杂的 I/O 依赖，AI 在编写这一层的代码时产生幻觉的概率大大降低，且单元测试极易生成和验证 5。

### **3.3 依赖注入与端口适配器**

为了将 core 与 infra 连接起来，必须使用依赖注入（Dependency Injection）。在 Rust 中，这通常通过泛型或动态分发（Dyn Trait）实现。

* **端口（Ports）**：在 core 中定义 trait UserRepository: Send \+ Sync {... }。  
* **适配器（Adapters）**：在 infra 中实现 struct PostgresUserRepository { pool: sqlx::PgPool }。  
* **注入**：在 api 或 desktop 的启动阶段（main.rs），初始化具体的适配器并将其封装在 Arc\<dyn UserRepository\> 中传递给应用状态（AppState）。这种模式允许在测试时轻松替换为 MockUserRepository 7。

## ---

**4\. 核心技术宪法：物理定律与约束**

为了确保生成的 Rust 代码在长时间维护中保持健壮，必须制定一套“技术宪法”，规定内存管理、并发模型及运行时选择的“物理定律”。这些规则在 spec.md 中被显式定义，强制 AI 遵守 4。

### **4.1 内存管理与所有权模型**

这是 Rust 开发中最容易出错的领域。技术宪法必须明确：

* **所有权策略**：对于实现 Copy trait 的小型结构体（如 ID、枚举），强制使用值传递；对于大型数据结构（如 Vec、String），优先使用借用（&）。但在跨异步任务传递时，**强制使用 std::sync::Arc** 进行共享所有权管理，严禁滥用 .clone() 来逃避生命周期检查 4。  
* **生命周期标注**：明确指示 AI 代理“除非绝对必要，避免在公有结构体中使用显式生命周期参数（\<'a\>）”。复杂的生命周期级联是导致 AI 生成代码无法通过编译的主要原因。推荐使用拥有所有权的类型（Owned Types）或 Box\<dyn Trait\> 来简化内存图谱 4。  
* **内部可变性**：明确区分 Mutex 和 RwLock。对于读多写少的全局状态（如配置、缓存），**强制要求使用 tokio::sync::RwLock** 以避免高并发下的性能瓶颈。严禁使用 std::sync::Mutex 在异步上下文中，以防止死锁 4。

### **4.2 并发与异步运行时 (Async Runtime)**

Rust 的异步生态存在割裂（Tokio vs Async-std）。为了避免兼容性灾难，宪法必须选边站队：

* **运行时锁定**：项目必须且仅能使用 **tokio (v1.x)**，并开启 full 特性。这是目前工业界最成熟的标准 1。  
* **阻塞禁令**：**严禁**在 async fn 中调用任何阻塞 I/O 函数（如 std::fs::read 或 std::thread::sleep）。AI 必须被指令使用 tokio::fs 或 tokio::time 的对应版本。违背此规则将导致运行时线程饥饿，这是极其隐蔽且严重的 Bug 4。  
* **任务模型**：并发任务使用 tokio::spawn。对于 CPU 密集型任务（如密码哈希），**必须**使用 tokio::task::spawn\_blocking 将其卸载到专用线程池，以免阻塞 Reactor 循环 4。

### **4.3 错误处理层级体系**

为了避免 unwrap() 满天飞的情况，需建立分层错误处理标准：

* **库级错误 (thiserror)**：在 core 和 infra 层，必须使用 thiserror crate 定义强类型的枚举错误（Enum Errors）。这允许上层调用者通过模式匹配（Pattern Matching）精确处理特定错误（如 UserNotFound vs DatabaseTimeout）9。  
* **应用级错误 (anyhow / AppError)**：  
  * 在 CLI 工具中，允许使用 anyhow::Result 以便快速捕获并打印错误回溯（Backtrace）。  
  * 在 Web API 中，必须定义全局的 AppError 枚举，该枚举实现 Axum::IntoResponse，将底层错误映射为标准的 HTTP 状态码和 JSON 响应。这确保了 API 响应的一致性，并防止内部系统细节泄露给前端 11。  
* **零恐慌政策**：宪法规定，在 src/ 目录下的逻辑代码中，**严禁**使用 panic\!, .unwrap(), .expect()。所有的不可恢复错误必须转化为 Result::Err 向上传播。AI 代理若违反此条，将被视为生成了不合格代码 4。

## ---

**5\. 接口层选型与实现：Axum 与 Tauri 的融合**

作为连接前端的桥梁，接口层的选型直接决定了全栈开发的体验。基于 2025 年的生态现状，**Axum** 是 Web 服务的唯一推荐，而 **Tauri v2** 则是桌面/移动端的标准 1。

### **5.1 Web 框架：为什么选择 Axum？**

尽管 Actix-web 性能强劲，但 Axum 凭借其基于 tower::Service 的模块化设计和与 Tokio 生态的无缝集成，已成为事实上的标准。

* **提取器（Extractors）模式**：Axum 的 State、Json、Path 提取器提供了声明式的请求处理方式，极大地增强了类型安全性。  
* **中间件复用**：由于基于 Tower，Axum 可以直接复用生态中已有的中间件（如超时、重试、限流），这对于构建健壮的微服务至关重要 14。  
* **AI 适应性**：Axum 的宏较少（相比 Rocket），代码结构更符合 Rust 标准语法，这使得 AI 代理更容易理解和生成正确的路由代码.7

### **5.2 桌面与移动端：Tauri v2 集成**

Tauri v2 带来了对移动端（iOS/Android）的支持，使得“一次编写，到处运行”成为可能。在架构上，Tauri 应用仅仅是 core 层的另一个消费者。

* **IPC 通信**：Tauri 的前端通过 IPC（进程间通信）调用 Rust 后端。本标准建议将 Tauri 的 Command 定义为对 core 服务接口的薄封装。  
* **事件驱动**：利用 Tauri v2 的事件系统（Events），后端可以主动向前端推送状态更新（如长任务进度），这比传统的 HTTP 轮询更加高效.13

## ---

**6\. 全栈闭环的核心：类型同步与 Specta**

“全栈闭环”的核心痛点在于：后端修改了数据结构，前端如何感知？传统的 Swagger/OpenAPI 生成方案往往存在滞后。本标准通过 **Specta** 实现真正的代码级类型同步 17。

### **6.1 从 rspc 到 Specta 的演进**

虽然 rspc 曾试图模仿 tRPC 提供端到端的类型安全，但鉴于其维护状态的不确定性（维护者已声明减少投入 19），本标准推荐采用更底层的 **Specta** 方案，这是一种更稳健、解耦的架构选择。

### **6.2 Specta 工作流**

在 shared crate 中，所有需要暴露给前端的结构体都必须派生 Type trait：

Rust

\#  
\#\[specta(export \= false)\] // 或者是具体的导出配置  
pub struct UserProfile {  
    pub id: Uuid,  
    pub username: String,  
    pub roles: Vec\<Role\>,  
}

* **自动化生成**：配置一个独立的测试或构建脚本，在每次编译时运行。该脚本利用 Specta 的反射能力，扫描所有标记了 Type 的结构体，并生成对应的 TypeScript 定义文件（bindings.ts）13。  
* **前端集成**：前端项目在 package.json 中引用生成的 bindings.ts。一旦后端修改了 UserProfile 的字段（例如将 username 改为 email），前端的 TypeScript 编译器会立即报错，指所有引用该字段的代码位置。  
* **Tauri 集成**：对于 Tauri 项目，使用 tauri-specta (v2) 可以直接生成封装好的 TypeScript 函数，使得前端调用 Rust 命令就像调用本地异步函数一样，且拥有完整的参数和返回值类型检查 13。

这一机制实现了物理意义上的“闭环”：**后端的代码变更是前端类型错误的直接触发源**，无需人工干预文档。

## ---

**7\. 持久化策略：SQLx 与数据库无关性**

在 ORM（如 Diesel/SeaORM）与原生 SQL 之间，本标准坚定选择 **SQLx**。其核心理由是：**编译期 SQL 检查** 9。

### **7.1 编译期验证的价值**

SQLx 允许开发者编写原生 SQL，并通过 query\! 宏在编译时连接数据库进行语法和类型检查。如果 SQL 语句中的列名写错，或者类型与数据库表定义不匹配，代码将无法编译。这消除了“运行时 SQL 错误”这一类别的 Bug，与 Rust 的安全哲学完美契合。

### **7.2 仓库模式与多数据库支持**

虽然 SQLx 提供了类型安全，但直接在业务逻辑中使用 SQL 会导致代码与特定数据库绑定。为了支持开发环境（SQLite）和生产环境（Postgres）的切换，必须实现**仓库模式（Repository Pattern）**。

* **Trait 定义**：在 core 层定义 trait UserRepository，包含 create, find\_by\_id 等抽象方法。  
* **泛型 vs 枚举**：对于支持多种数据库，存在两种流派。本标准推荐**泛型 Trait \+ 依赖注入**的方式。虽然 Rust 的 async trait 需要 BoxFuture（或使用 async\_trait 宏），但这提供了最清晰的解耦。另一种轻量级方案是使用枚举（Enum Dispatch），即定义一个 DbRepo 枚举，包含 Sqlite(SqliteRepo) 和 Postgres(PostgresRepo) 变体，这在数据库类型固定且较少时更为简便，且能避免动态分发的开销 22。  
* **迁移管理**：强制使用 sqlx-cli 管理数据库迁移（Migrations），确保数据库 Schema 的变更也是版本化和可追溯的 24。

## ---

**8\. 安全与认证体系**

安全不是事后的补丁，而是架构的基石。

### **8.1 认证 (Authentication)**

* **密码哈希**：严禁明文存储密码。标准强制使用 **Argon2** 算法（通过 argon2 crate），这是目前抗 GPU/ASIC 破解最强的哈希算法 4。  
* **JWT 策略**：对于无状态 API，使用 jsonwebtoken crate 生成和验证 Token。Token 必须包含过期时间（exp），且签名密钥必须从环境变量加载，严禁硬编码。

### **8.2 会话管理 (Session Management)**

对于需要保持状态的 Web 应用，推荐使用 tower-sessions 或 axum-sessions。

* **存储后端**：生产环境必须使用 Redis 或数据库作为会话存储（Session Store），而非内存，以支持后端的水平扩展 26。  
* **Cookie 安全**：必须设置 HttpOnly, Secure, SameSite 属性，防止 XSS 和 CSRF 攻击。

## ---

**9\. 规范驱动开发 (SDD) 实战指南**

为了将上述理论转化为实践，我们提供一份针对 AI 代理的 spec.md 编写模板。这不仅是文档，更是控制 AI 生成代码质量的指令集。

### **9.1 模板结构**

# **模块规范：用户认证服务 (UserAuth)**

## **1\. 概述**

实现基于邮箱/密码的用户注册与登录功能，产出 JWT Token。

## **2\. 数据模型 (src/models.rs)**

使用以下 Rust 代码定义核心结构，确保派生 Specta 类型：rust

pub struct User {

pub id: Uuid,

pub email: String,

\#\[serde(skip)\] // 严禁将哈希密码序列化到前端

pub password\_hash: String,

}

\#\# 3\. 接口定义 (src/api/handlers.rs)  
\- \*\*POST /register\*\*: 接收 \`RegisterRequest\` DTO。  
  \- 校验邮箱格式。  
  \- 使用 Argon2 哈希密码 (必须在 \`spawn\_blocking\` 中执行)。  
  \- 写入数据库 (UserRepository)。  
  \- 返回 201 Created。  
\- \*\*POST /login\*\*: 接收 \`LoginRequest\` DTO。  
  \- 查询用户，若不存在返回 401。  
  \- 验证密码 (Argon2)。  
  \- 生成 JWT，有效期 2 小时。

\#\# 4\. 技术约束 (Technical Constitution)  
\- \*\*并发\*\*: 数据库操作必须异步。密码哈希必须使用 \`tokio::task::spawn\_blocking\`。  
\- \*\*错误处理\*\*: 定义 \`AuthError\` 枚举，包含 \`WrongCredentials\`, \`UserAlreadyExists\`。必须实现 \`IntoResponse\`。  
\- \*\*依赖\*\*: 仅限使用 \`axum\`, \`sqlx\`, \`argon2\`, \`jsonwebtoken\`。禁止引入未审核的 crate。

### **9.2 执行策略：一次性编译原则**

在与 AI 交互时，需遵循“黄金法则”：**原子化重构**。当 AI 需要修改底层 Struct 或 Trait 时，指令它必须在一个批次中识别并更新代码库中所有的引用点。如果 AI 分步修改，极易导致中间状态的编译错误，进而引发“打地鼠”式的修复循环，破坏上下文的稳定性 4。

## ---

**10\. 结论与展望**

本报告所定义的 Rust 后端系统设计标准，并非单纯的技术堆栈罗列，而是一套适应 AI 时代特征的工程方法论。

1. **闭环的实现**：通过 **Workspace \+ Headless Core** 架构，我们实现了业务逻辑的跨端复用；通过 **Specta \+ TypeScript**，我们实现了前后端类型的硬连接；通过 **SDD**，我们实现了从自然语言需求到高质量 Rust 代码的闭环。  
2. **角色的转变**：开发者不再是与借用检查器搏斗的工匠，而是定义“技术宪法”的立法者。通过 CLAUDE.md 和 spec.md，我们将 Rust 的最佳实践固化为 AI 可执行的规则。  
3. **未来的趋势**：随着 Rust 异步生态的进一步统一（如 async\_fn\_in\_trait 的稳定），以及 AI 对长上下文理解能力的提升，全栈开发的门槛将进一步降低。但无论工具如何进化，“类型安全”与“架构约束”始终是构建可靠系统的物理定律。

这套标准为 2025 年及以后的全栈开发提供了一个兼具极其强大的性能基座与极高开发效率的蓝图。

### ---

**参考文献索引**

**表 1: 核心技术栈清单 (宪法级依赖)**

| 领域 | 推荐选型 | 选择理由 |
| :---- | :---- | :---- |
| **语言标准** | Rust 2021/2024 | 内存安全，零 GC，高性能 |
| **异步运行时** | Tokio (v1.x) | 工业标准，生态最全，极其稳定 1 |
| **Web 框架** | Axum | 模块化，类型安全，与 Tokio/Tower 完美融合 14 |
| **数据库层** | SQLx | 编译期 SQL 校验，纯异步实现 9 |
| **序列化** | Serde | Rust 数据序列化的通用标准 4 |
| **前后端桥接** | Specta | 自动生成 TypeScript 类型，维护性优于 rspc 17 |
| **错误处理** | thiserror / anyhow | 库与其应用的错误分离，标准做法 10 |
| **桌面框架** | Tauri v2 | 资源占用极低，支持移动端，安全性高 13 |

**表 2: AI 代理内存管理指南**

| 数据类型 | 操作场景 | 强制策略 | 原因 |
| :---- | :---- | :---- | :---- |
| i32, bool, Uuid | 传递/赋值 | 按值传递 (Copy) | 成本极低，避免生命周期标注复杂度 |
| String, Vec\<T\> | 只读访问 | 借用 (\&T) | 避免不必要的内存分配 |
| String, Vec\<T\> | 跨线程/异步 | Arc\<T\> | 必须使用原子引用计数，确保线程安全 |
| 共享可变状态 | 读多写少 | RwLock\<T\> | 相比 Mutex 显著提升并发读取性能 4 |

（报告结束）

#### **引用的著作**

1. Building Rust Web Apps \- Shuttle.dev, 访问时间为 一月 27, 2026， [https://www.shuttle.dev/blog/2025/11/12/build-rust-web-apps](https://www.shuttle.dev/blog/2025/11/12/build-rust-web-apps)  
2. The Next-Generation Flexible Map Engine for Advanced GIS Visualization. :: FOSS4G 2025 :: pretalx \- Events, 访问时间为 一月 27, 2026， [https://talks.osgeo.org/foss4g-2025/talk/RM9RHS/](https://talks.osgeo.org/foss4g-2025/talk/RM9RHS/)  
3. Rust Headless: a good solution for developing a simulation?, 访问时间为 一月 27, 2026， [https://www.reddit.com/r/rust/comments/1q0twpf/rust\_headless\_a\_good\_solution\_for\_developing\_a/](https://www.reddit.com/r/rust/comments/1q0twpf/rust_headless_a_good_solution_for_developing_a/)  
4. Rust 项目规范与 AI 开发  
5. The best way to structure Rust web services \- LogRocket Blog, 访问时间为 一月 27, 2026， [https://blog.logrocket.com/best-way-structure-rust-web-services/](https://blog.logrocket.com/best-way-structure-rust-web-services/)  
6. Master Hexagonal Architecture in Rust \- How To Code It, 访问时间为 一月 27, 2026， [https://www.howtocodeit.com/guides/master-hexagonal-architecture-in-rust](https://www.howtocodeit.com/guides/master-hexagonal-architecture-in-rust)  
7. Dependency Injection Strategies in Axum and Actix Web | Leapcell, 访问时间为 一月 27, 2026， [https://leapcell.io/blog/dependency-injection-strategies-in-axum-and-actix-web](https://leapcell.io/blog/dependency-injection-strategies-in-axum-and-actix-web)  
8. Case Study: Using Traits in Rust for Clean Architecture \- Michael de Silva, 访问时间为 一月 27, 2026， [https://desilva.io/posts/case-study-using-traits-in-rust-for-clean-architecture](https://desilva.io/posts/case-study-using-traits-in-rust-for-clean-architecture)  
9. launchbadge/sqlx: The Rust SQL Toolkit. An async, pure Rust SQL crate featuring compile-time checked queries without a DSL. Supports PostgreSQL, MySQL, and SQLite. \- GitHub, 访问时间为 一月 27, 2026， [https://github.com/launchbadge/sqlx](https://github.com/launchbadge/sqlx)  
10. thiserror, anyhow, or How I Handle Errors in Rust Apps | Alex Fedoseev, 访问时间为 一月 27, 2026， [https://alexfedoseev.com/blog/post/thiserror-anyhow-or-how-i-handle-errors-in-rust-apps](https://alexfedoseev.com/blog/post/thiserror-anyhow-or-how-i-handle-errors-in-rust-apps)  
11. Elegant Error Handling in Axum/Actix Web with IntoResponse \- Leapcell, 访问时间为 一月 27, 2026， [https://leapcell.io/blog/elegant-error-handling-in-axum-actix-web-with-intoresponse](https://leapcell.io/blog/elegant-error-handling-in-axum-actix-web-with-intoresponse)  
12. axum::error\_handling \- Rust \- Docs.rs, 访问时间为 一月 27, 2026， [https://docs.rs/axum/latest/axum/error\_handling/index.html](https://docs.rs/axum/latest/axum/error_handling/index.html)  
13. v2 \- specta-rs, 访问时间为 一月 27, 2026， [https://specta.dev/docs/tauri-specta/v2](https://specta.dev/docs/tauri-specta/v2)  
14. The Ultimate Guide to Axum: From Hello World to Production in Rust (2025) \- Shuttle.dev, 访问时间为 一月 27, 2026， [https://www.shuttle.dev/blog/2023/12/06/using-axum-rust](https://www.shuttle.dev/blog/2023/12/06/using-axum-rust)  
15. Decrusting the axum crate \- YouTube, 访问时间为 一月 27, 2026， [https://www.youtube.com/watch?v=Wnb\_n5YktO8](https://www.youtube.com/watch?v=Wnb_n5YktO8)  
16. specta-rs/tauri-specta: Completely typesafe Tauri commands \- GitHub, 访问时间为 一月 27, 2026， [https://github.com/specta-rs/tauri-specta](https://github.com/specta-rs/tauri-specta)  
17. Overview \- specta-rs, 访问时间为 一月 27, 2026， [https://specta.dev/docs/rspc](https://specta.dev/docs/rspc)  
18. Crate rspc \- Rust \- Docs.rs, 访问时间为 一月 27, 2026， [https://docs.rs/rspc](https://docs.rs/rspc)  
19. Stepping back from rspc's development · specta-rs rspc · Discussion \#351 \- GitHub, 访问时间为 一月 27, 2026， [https://github.com/specta-rs/rspc/discussions/351](https://github.com/specta-rs/rspc/discussions/351)  
20. Generate TypeScript Bindings for Rust \- Rustfinity, 访问时间为 一月 27, 2026， [https://www.rustfinity.com/blog/generate-typescript-bindings-for-rust](https://www.rustfinity.com/blog/generate-typescript-bindings-for-rust)  
21. Illustrated Guide to SQLX, 访问时间为 一月 27, 2026， [https://jmoiron.github.io/sqlx/](https://jmoiron.github.io/sqlx/)  
22. Database abstraction layer \- accessing underlying connection \- Rust Users Forum, 访问时间为 一月 27, 2026， [https://users.rust-lang.org/t/database-abstraction-layer-accessing-underlying-connection/126735](https://users.rust-lang.org/t/database-abstraction-layer-accessing-underlying-connection/126735)  
23. Enum vs. Generic with Trait pros/cons \- \#3 by cole-miller \- help \- Rust Users Forum, 访问时间为 一月 27, 2026， [https://users.rust-lang.org/t/enum-vs-generic-with-trait-pros-cons/50069/3](https://users.rust-lang.org/t/enum-vs-generic-with-trait-pros-cons/50069/3)  
24. sqlx \- Rust \- Docs.rs, 访问时间为 一月 27, 2026， [https://docs.rs/sqlx/latest/sqlx/](https://docs.rs/sqlx/latest/sqlx/)  
25. Authentication — list of Rust libraries/crates // Lib.rs, 访问时间为 一月 27, 2026， [https://lib.rs/authentication](https://lib.rs/authentication)  
26. axum\_session \- Rust \- Docs.rs, 访问时间为 一月 27, 2026， [https://docs.rs/axum\_session](https://docs.rs/axum_session)  
27. actix\_session \- Rust \- Docs.rs, 访问时间为 一月 27, 2026， [https://docs.rs/actix-session/latest/actix\_session/](https://docs.rs/actix-session/latest/actix_session/)