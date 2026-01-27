# Rust Code Style Guidelines

本文档定义了本项目的代码编写标准。旨在统一代码风格，减少代码审查中的低级争论，并确保系统的可维护性与高性能。

所有贡献者在提交 Pull Request 前，**必须** 确保代码符合本规范。

---

## 1. 工具链与自动化 (Tooling & Automation)

我们坚持“工具优于约定”的原则。凡是可以通过工具自动检查的规则，必须通过工具执行。

### 1.1 格式化 (Formatting)
* **强制执行**：必须使用 `rustfmt` 进行格式化。
* **配置**：项目根目录下的 `rustfmt.toml` 是格式标准的唯一真理。
* **操作**：提交代码前请运行：
    ```bash
    cargo fmt --all
    ```

### 1.2 静态分析 (Linting)
* **强制执行**：必须通过 `clippy` 检查，且**零警告 (Zero Warnings)**。
* **CI 标准**：CI 流程将视警告为错误 (`-D warnings`)。
* **例外处理**：如果必须忽略某个 lint，必须在代码上方添加注释说明原因：
    ```rust
    // ALLOW(clippy::too_many_arguments): 保持 C FFI 兼容性，无法减少参数
    #[allow(clippy::too_many_arguments)]
    fn complex_ffi_func(...) {}
    ```

---

## 2. 命名规范 (Naming Conventions)

遵循 [Rust RFC 430](https://github.com/rust-lang/rfcs/blob/master/text/0430-naming-conventions.md) 标准。

| 元素类型 (Item) | 风格 (Style) | 示例 (Example) | 备注 |
| :--- | :--- | :--- | :--- |
| **Crate / Module** | `snake_case` | `data_processor` | 避免在 crate 名中使用连字符 `-` (虽然允许，但推荐下划线) |
| **Struct / Enum / Trait** | `UpperCamelCase` | `HttpRequest`, `UserStatus` | 应当是名词 |
| **Function / Method** | `snake_case` | `get_user_by_id` | 应当是动词或动宾短语 |
| **Variable (Local)** | `snake_case` | `user_count` | |
| **Const / Static** | `SCREAMING_SNAKE`| `MAX_RETRY_TIMEOUT` | |
| **Generic Type** | `UpperCamelCase` | `T`, `K`, `V`, `Input` | 简单泛型用单字母，复杂场景用具名 |
| **Macro** | `snake_case!` | `generate_handler!` | |

### 2.1 特殊约定
* **Getter 方法**：遵循 Rust 惯例，**不要** 加 `get_` 前缀。
    * ✅ `fn name(&self) -> &str`
    * ❌ `fn get_name(&self) -> &str`
* **类型转换**：
    * `as_` (零开销/低开销): `as_str()`
    * `to_` (昂贵/克隆): `to_string()`
    * `into_` (消耗所有权): `into_vec()`

---

## 3. 异步编程规范 (Async Rust)

由于异步环境的特殊性，以下规则直接关系到系统的吞吐量和稳定性，**必须严格遵守**。

### 3.1 严禁阻塞执行器 (Do Not Block)
在 `async` 上下文中，**绝对禁止** 调用阻塞操作。这会阻塞整个 Runtime 线程，导致系统假死。

* ❌ **禁止**：
    * `std::thread::sleep`
    * `std::sync::Mutex` (当持有锁跨越 `.await` 时)
    * 同步文件 I/O (`std::fs`)
    * 密集的 CPU 计算循环 (>100µs)
* ✅ **正确做法**：
    * 使用 `tokio::time::sleep`。
    * 对于文件 I/O 或 CPU 密集任务，使用 `tokio::task::spawn_blocking`。

### 3.2 锁的使用 (Locks: std vs tokio)
死锁的主要来源是错误地混用锁。

* **场景 A：持有锁期间不需要 `.await`**
    * 使用：`std::sync::Mutex`
    * 理由：性能更高，开销更小。
* **场景 B：持有锁期间必须 `.await` (如 I/O)**
    * 使用：`tokio::sync::Mutex`
    * 理由：标准库的 Mutex 跨越 await 点会导致死锁或 Send 检查失败。

### 3.3 结构化并发 (Structured Concurrency)
避免“发射后不管 (`Fire and Forget`)”式的 `tokio::spawn`，除非你明确不需要管理其生命周期。

* ❌ **Bad**:
    ```rust
    tokio::spawn(task_a());
    tokio::spawn(task_b());
    // 如果 task_a panic，主流程无法感知
    ```
* ✅ **Good**:
    ```rust
    // 等待所有任务完成，且能捕获错误
    let (res_a, res_b) = tokio::try_join!(task_a(), task_b())?;
    ```

### 3.4 Send 约束
所有 `Future` 必须是 `Send` 的。
* **检查**：不要在 `.await` 跨度中持有 `Rc`, `RefCell` 或原始指针。
* **修正**：使用 `Arc` 替代 `Rc`，使用 `Mutex`/`RwLock` 替代 `RefCell`。

---

## 4. 错误处理 (Error Handling)

### 4.1 禁止 Panic
* **严禁** 在核心业务代码中使用 `unwrap()` 或 `expect()`。
* **例外**：
    * 单元测试 (`#[test]`)。
    * 程序启动时的配置加载（如果配置错误，程序本就该挂掉）。
    * 拥有 100% 安全性证明的逻辑（需添加注释 `// SAFETY: ...`）。

### 4.2 错误传播与上下文
不要只返回 `Err`，要告诉调用者发生了什么。
* 使用 `anyhow` (App) 或 `thiserror` (Lib)。
* **关键**：为错误添加上下文。

```rust
// ✅ Good
File::open(&path).with_context(|| format!("无法读取配置文件: {:?}", path))?;
```

## 5. 代码习惯与最佳实践 (Idioms)

### 5.1 数据类型
* **NewType 模式**：避免“原始类型迷恋 (Primitive Obsession)”。
    * ❌ `fn pay(amount: f64)`
    * ✅ `struct Amount(f64); fn pay(amount: Amount)`
* **Option 优于特殊值**：永远不要用 `-1`、`0` 或空字符串来表示“不存在”。

### 5.2 迭代器 (Iterators)
优先使用迭代器链式调用，而非 `for` 循环。迭代器通常更快（边界检查优化）且更具表达力。

```rust
// ✅ Good
let active_users: Vec<_> = users.iter()
    .filter(|u| u.is_active)
    .map(|u| u.name.clone())
    .collect();
```

## 6. 文档规范 (Documentation)

* **API 文档**：所有 `pub` 的结构体、函数、Trait 必须包含 `///` 文档注释。
* **模块文档**：每个文件头部推荐使用 `//!` 简述模块功能。
* **示例代码**：文档中必须包含 `# Examples` 章节，这不仅是文档，更是可执行的测试。

```rust
/// 计算两数之和。
///
/// # Examples
///
/// ```
/// let n = my_crate::add(1, 2);
/// assert_eq!(n, 3);
/// ```
pub fn add(a: i32, b: i32) -> i32 { ... }
```

## 7. 测试 (Testing)

* **单元测试**：放在源文件底部的 mod tests 模块中。

* **集成测试**：放在项目根目录的 tests/ 文件夹中。

* **覆盖原则**：核心算法必须包含边缘情况（Edge Cases）测试。


## 8. 版本控制 (Git)

遵循 **Conventional Commits** 规范：

* `feat`: 新功能
* `fix`: 修复 Bug
* `docs`: 文档变更
* `style`: 格式调整（不影响代码逻辑）
* `refactor`: 重构（无新功能，无 Bug 修复）
* `perf`: 性能优化
* `test`: 增加测试
* `chore`: 构建过程或辅助工具的变动