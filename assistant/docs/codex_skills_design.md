# Codex 核心运行设计与插件（Skills）支持设计

> 目的：整理 Codex 的核心运行架构与 Skills 机制，作为 assistant v2 的可借鉴设计参考。
> 本文基于仓库 `codex` 的实现代码阅读整理（Rust 版本）。

## 1. 术语与总体目标

- **Codex Core**：负责会话、任务调度、模型调用、历史与事件管理的核心执行引擎。
- **Skills**：一种插件式能力包装，用于把本地“操作指南 + 资源”注入到模型上下文。
- **SKILL.md**：技能的主文件（包含 frontmatter + 正文），既作为元信息，也作为可注入的指令内容。

目标：
- 让模型在合适时机读取具体技能指令（SKILL.md）并使用其脚本/资源。
- 允许按环境/用户/项目维度加载与禁用技能。

## 2. 核心运行设计（Codex 运行链路）

### 2.1 会话启动流程（Session Spawn）
入口：`codex-rs/core/src/codex.rs::Codex::spawn`

核心步骤：
1. 读取并合并配置（Config + ConfigLayerStack）
2. 初始化 Models / ExecPolicy / SkillsManager
3. **加载技能清单**（`skills_manager.skills_for_config`）
4. 生成基础系统指令与用户指令（包含 Skills 列表）
5. 创建 Session

特征：
- Skills 的“清单”在 session 初始化时就准备好
- Skills 正文并未立即注入，只在“显式触发”时注入

### 2.2 Turn 处理（核心循环）
入口：`codex-rs/core/src/codex.rs` 的 turn 处理逻辑

关键步骤：
1. 将 UserInput 构建成 ResponseItem
2. **调用 skill_injection**（如果输入包含显式 Skill）
3. 将 skill_items 记录到对话历史（即注入 SKILL.md 正文）
4. 组装模型调用输入（history + skill items）
5. 执行模型推理 + 工具调用

### 2.3 Skills 注入机制（重要设计）
文件：`codex-rs/core/src/skills/injection.rs`

规则：
- 只有当输入里出现 `UserInput::Skill { name, path }` 时才注入
- 注入内容来自读取磁盘上的 `SKILL.md` 完整内容
- 若读取失败，发 warning

优点：
- 按需加载，不污染上下文
- 安全可控（用户/系统显式选择）

## 3. Skills 支持设计（插件机制）

### 3.1 Skills 目录与多层级来源
入口：`skills/loader.rs` + `skills/manager.rs`

Skills Root 由多个层级组成：
- Repo skills（项目内）
- User skills（用户目录）
- System skills（内置技能缓存）
- Admin skills（系统级目录）

加载逻辑：
- 多目录扫描，后加载覆盖前加载
- 根据 config 层决定禁用列表

### 3.2 SKILL.md 结构与职责
典型 Skill 目录结构：
```
skills/<skill-name>/
  SKILL.md
  scripts/
  references/
  assets/
```

`SKILL.md` = 由两部分组成：
- **frontmatter（YAML）**：name、description、short-description
- **正文**：工具说明、操作指令、资源引用

作用：
- frontmatter 用于技能发现（skills list）
- 正文在触发时注入模型上下文

### 3.3 Skills 列表与使用规则
渲染文件：`skills/render.rs` → `project_doc.rs`

会话初始化时会把以下内容加入 user_instructions：
- skills 列表（name + description + SKILL.md 路径）
- skills 使用规则（选择、读取顺序、资源使用策略）

目的：
- 引导模型“何时使用 skill”
- 模型知晓 skill 的文件路径与名称

### 3.4 Skills 触发方式
`UserInput::Skill` 是唯一注入触发方式。

触发来源可以是：
- UI/CLI 显式选择某个 skill
- 系统自动把 skill 插入输入（如果你实现规则引擎）

### 3.5 Skills 配置与禁用
- `SkillsManager::disabled_paths_from_stack()`
- 通过 config 的 `skills.config` 列表禁用/启用

能力：
- 按 layer 配置（user / project / system）
- 精确到 SKILL.md 路径

## 4. 可借鉴的设计原则（建议用于 assistant v2）

### 4.1 “技能清单”和“技能注入”分离
- 清单：会话创建时加载（轻量）
- 注入：只有显式触发时读取 SKILL.md 正文
- 避免无意义上下文膨胀

### 4.2 技能实体保持文件级原子性
- 以 SKILL.md 为主
- scripts/references/assets 全在同一目录
- 支持多目录加载与覆盖

### 4.3 Skills 作为“可控插件”而不是默认 prompt
- 使用显示/明确触发
- 可配禁用/启用策略

### 4.4 Skills + Event 流 + Tool 执行分离
- Skills 仅负责“操作指南”与“资源输入”
- Tool 执行仍走统一工具链

## 5. assistant v2 的可落地方案（建议）

### 5.1 v2 目标架构
- 核心 runtime 稳定：
  - Session / Turn / Events / Tool loop 固化
- 插件化能力模块：
  - Skills / Hooks / Tool Packs

### 5.2 技能（Skill）设计迁移
建议采用 Codex 方式：
1. **Skills 扫描器**：扫描 skills 目录读取 SKILL.md
2. **Skills 清单渲染**：把 skills list + usage rules 放入 system/user instructions
3. **显式触发**：支持手动触发（UI / 规则）
4. **按需注入**：只在触发时注入正文
5. **多层级覆盖**：project / user / system

### 5.3 与现有 assistant v1 的兼容策略
- 复用当前 SkillLoader 扫描目录逻辑
- 改为“两阶段模式”：
  - 阶段 1：加载技能 metadata
  - 阶段 2：触发时加载 SKILL.md 内容

## 6. 关键参考文件列表（Codex）

- **技能加载**：`codex-rs/core/src/skills/loader.rs`
- **技能管理**：`codex-rs/core/src/skills/manager.rs`
- **技能注入**：`codex-rs/core/src/skills/injection.rs`
- **技能渲染**：`codex-rs/core/src/skills/render.rs`
- **SKILL.md schema**：`codex-rs/core/src/skills/assets/samples/skill-creator/SKILL.md`
- **主流程**：`codex-rs/core/src/codex.rs`
- **协议接口**：`codex-rs/protocol/src/protocol.rs`

---

如需我基于 assistant v2 现状，继续输出：
- v2 的模块规划结构图
- skills 的具体接口定义（Python 版）
- 与事件系统/工具系统的对接方案

请直接说方向。
