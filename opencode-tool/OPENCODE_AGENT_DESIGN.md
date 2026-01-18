# OpenCode Agent 设计文档

本文档详细描述了 opencode 中 Agent 的关键设计实现，包括架构、内置工具、记忆系统和计划执行机制。

---

## 1. Agent 设计实现

### 核心架构
**位置**: `opencode/packages/opencode/src/agent/agent.ts`

系统不是单一的 Agent 类，而是**配置驱动的 Agent 框架**。关键组件包括：

#### Agent Info Schema (Lines 20-44)
```typescript
export const Info = z.object({
  name: z.string(),
  description: z.string().optional(),
  mode: z.enum(["subagent", "primary", "all"]),
  native: z.boolean().optional(),
  hidden: z.boolean().optional(),
  topP: z.number().optional(),
  temperature: z.number().optional(),
  color: z.string().optional(),
  permission: PermissionNext.Ruleset,
  model: z.object({
    modelID: z.string(),
    providerID: z.string(),
  }).optional(),
  prompt: z.string().optional(),
  options: z.record(z.string(), z.any()),
  steps: z.number().int().positive().optional(),
})
```

#### Agent 类型 (Lines 70-195)

系统定义了几个内置的 Agent：

1. **build** - Primary agent 用于构建/实现阶段
   - 有 `question: "allow"` 权限
   - 有 `plan_enter: "allow"` 权限
   - 模式: "primary"
   - Native: true

2. **plan** - Primary agent 用于规划阶段
   - 有 `question: "allow"` 权限
   - 有 `plan_exit: "allow"` 权限
   - 只能编辑 `.opencode/plans/*.md` 文件
   - 模式: "primary"
   - Native: true

3. **general** - Subagent 用于研究和多步骤任务
   - 可并行执行多个工作单元
   - `todoread: "deny"`, `todowrite: "deny"`
   - 模式: "subagent"

4. **explore** - 快速代码库探索 subagent
   - 专门用于查找文件、搜索代码
   - 限于只读工具: grep, glob, list, bash, webfetch, websearch, codesearch, read
   - 模式: "subagent"

5. **compaction** - 隐藏的会话压缩 agent
   - 权限: `*": "deny"`
   - 模式: "primary"
   - Hidden: true
   - Prompt: 专门用于摘要

6. **title** - 隐藏的线程标题生成 agent
   - Temperature: 0.5
   - 模式: "primary"
   - Hidden: true

7. **summary** - 隐藏的对话摘要 agent
   - 模式: "primary"
   - Hidden: true

#### Agent 生成 (Lines 274-310)
```typescript
export async function generate(input: { description: string; model?: {...} }) {
  // 使用 LLM 生成 agent 配置
  const result = await generateObject({
    temperature: 0.3,
    messages: [...systemMessages, {role: "user", content: `Create an agent...`}],
    schema: z.object({
      identifier: z.string(),
      whenToUse: z.string(),
      systemPrompt: z.string(),
    }),
  })
  return result.object
}
```

---

## 2. 内置工具

### 工具注册架构
**位置**: `opencode/packages/opencode/src/tool/registry.ts`

工具系统使用**注册表模式**，支持延迟加载：

#### 注册函数
- `all()` - 返回所有可用工具 (lines 91-116)
- `ids()` - 返回工具 IDs (lines 118-120)
- `tools(providerID, agent)` - 返回为 agent 初始化的工具 (lines 122-142)
- `register(tool)` - 注册自定义工具 (lines 81-89)

#### 内置工具列表 (Lines 95-114)
```typescript
return [
  InvalidTool,
  ...(Flag.OPENCODE_CLIENT in ["app", "cli", "desktop"] ? [QuestionTool] : []),
  BashTool,
  ReadTool,
  GlobTool,
  GrepTool,
  EditTool,
  WriteTool,
  TaskTool,
  WebFetchTool,
  TodoWriteTool,
  TodoReadTool,
  WebSearchTool,
  CodeSearchTool,
  SkillTool,
  ...(Flag.OPENCODE_EXPERIMENTAL_LSP_TOOL ? [LspTool] : []),
  ...(config.experimental?.batch_tool === true ? [BatchTool] : []),
  ...(Flag.OPENCODE_EXPERIMENTAL_PLAN_MODE ? [PlanExitTool, PlanEnterTool] : []),
  ...custom,
]
```

### 各工具实现详解

#### Bash Tool
**位置**: `opencode/packages/opencode/src/tool/bash.ts` (Lines 1-258)

**特性**:
- 使用 tree-sitter bash 解析器解析 bash 命令
- 检测外部目录访问并请求权限
- 跟踪修改的目录（如 `cd`, `rm`, `cp`, `mv`, `mkdir`, `touch`, `chmod`, `chown`）
- 默认超时: 2 分钟 (120,000ms)
- 支持通过 `timeout` 参数自定义超时
- 使用元数据更新实时流式输出
- 中止/超时时终止进程树

**关键参数**:
- `command`: string - 要执行的 bash 命令
- `timeout`: number - 可选的超时时间（毫秒）
- `workdir`: string - 工作目录（默认为 Instance.directory）
- `description`: string - 清晰的 5-10 词描述

#### Read Tool
**位置**: `opencode/packages/opencode/src/tool/read.ts` (Lines 1-201)

**特性**:
- 基于行的分页读取文件
- 支持图片/PDF 作为附件（base64 编码）
- 通过扩展名和内容分析检测二进制文件
- 默认: 最多 2000 行，50KB 最大值
- 输出格式带行号: `00001| content`
- 错误时建议相似文件名

**关键参数**:
- `filePath`: string - 文件绝对路径
- `offset`: number - 开始读取的行号（从 0 开始）
- `limit`: number - 要读取的行数（默认 2000）

#### Edit Tool
**位置**: `opencode/packages/opencode/src/tool/edit.ts` (Lines 1-646)

**特性**:
- 多种模糊匹配替换器策略:
  1. `SimpleReplacer` - 精确匹配
  2. `LineTrimmedReplacer` - 修剪行匹配
  3. `BlockAnchorReplacer` - 首/末行锚定 + 相似度评分
  4. `WhitespaceNormalizedReplacer` - 空格不敏感匹配
  5. `IndentationFlexibleReplacer` - 缩进不敏感匹配
  6. `EscapeNormalizedReplacer` - 转义序列处理
  7. `TrimmedBoundaryReplacer` - 修剪边界匹配
  8. `ContextAwareReplacer` - 上下文匹配
  9. `MultiOccurrenceReplacer` - 多次出现处理
  10. `EscapeNormalizedReplacer` - 转义序列标准化
- Levenshtein 距离算法用于相似度匹配 (lines 156-172)
- 通过 `FileTime.withLock()` 实现文件锁定
- LSP 诊断集成
- 使用 `createTwoFilesPatch()` 生成差异

**关键参数**:
- `filePath`: string - 文件绝对路径
- `oldString`: string - 要替换的文本
- `newString`: string - 替换文本
- `replaceAll`: boolean - 替换所有出现（默认 false）

#### Write Tool
**位置**: `opencode/packages/opencode/src/tool/write.ts` (Lines 1-81)

**特性**:
- 完全覆盖文件
- 为权限请求生成差异
- 写入时进行 LSP 诊断
- 支持新文件和现有文件

**关键参数**:
- `filePath`: string - 绝对路径
- `content`: string - 要写入的内容

#### Glob Tool
**位置**: `opencode/packages/opencode/src/tool/glob.ts` (Lines 1-78)

**特性**:
- 使用 ripgrep 进行文件模式匹配
- 限制: 最多 100 个文件
- 按修改时间排序（最新的在前）
- 截断警告

**关键参数**:
- `pattern`: string - Glob 模式
- `path`: string - 要搜索的目录（可选，默认为当前目录）

#### Grep Tool
**位置**: `opencode/packages/opencode/src/tool/grep.ts` (Lines 1-154)

**特性**:
- 通过 ripgrep 进行正则模式搜索
- 文件包含过滤
- 最多 100 个结果，截断警告
- 输出格式: `Line {lineNum}: {text}`

**关键参数**:
- `pattern`: string - 正则模式
- `path`: string - 要搜索的目录（可选）
- `include`: string - 要包含的文件模式（如 `*.js`, `*.{ts,tsx}`）

#### Task Tool
**位置**: `opencode/packages/opencode/src/tool/task.ts` (Lines 1-189)

**特性**:
- 启动子代理进行专门任务
- 创建具有特定权限的嵌套会话
- 默认禁用子代理的 todo 和 task 工具
- 通过 Bus 事件流式传输工具执行进度
- 子代理会话跟踪

**关键参数**:
- `description`: string - 3-5 词描述
- `prompt`: string - 代理任务
- `subagent_type`: string - 代理类型 (explore, general 等)
- `session_id`: string - 要继续的现有会话（可选）
- `command`: string - 触发命令（可选）

#### Todo Tools
**位置**: `opencode/packages/opencode/src/tool/todo.ts` (Lines 1-53)

**特性**:
- `TodoWriteTool`: 更新任务列表
- `TodoReadTool`: 读取任务列表
- 存储在 Storage 中的 `["todo", sessionID]`

**关键参数**:
- `todos`: 对象数组，包含:
  - `content`: string - 简要任务描述
  - `status`: "pending" | "in_progress" | "completed" | "cancelled"
  - `priority`: "high" | "medium" | "low"
  - `id`: string - 唯一标识符

#### WebSearch Tool
**位置**: `opencode/packages/opencode/src/tool/websearch.ts` (Lines 1-150)

**特性**:
- 通过 `https://mcp.exa.ai` 进行基于 MCP 的搜索
- SSE (Server-Sent Events) 流式传输
- 25 秒超时
- 搜索类型: auto, fast, deep

**关键参数**:
- `query`: string - 搜索查询
- `numResults`: number - 要返回的结果数（默认 8）
- `livecrawl`: "fallback" | "preferred"
- `type`: "auto" | "fast" | "deep"
- `contextMaxCharacters`: number - 最大上下文字符数（默认 10000）

#### Skill Tool
**位置**: `opencode/packages/opencode/src/tool/skill.ts` (Lines 1-75)

**特性**:
- 从 SKILL.md 文件加载自定义技能
- 按 agent 权限过滤
- 显示带描述的可用技能
- 使用 ConfigMarkdown 解析器解析 markdown

**关键参数**:
- `name`: string - 技能标识符

#### Batch Tool (Experimental)
**位置**: `opencode/packages/opencode/src/tool/batch.ts` (Lines 1-175)

**特性**:
- 并行执行多个工具（最多 10 个）
- 不允许嵌套 batch 调用
- 过滤掉 MCP/环境工具
- 聚合结果

**关键参数**:
- `tool_calls`: `{tool: string, parameters: object}` 数组

#### MultiEdit Tool
**位置**: `opencode/packages/opencode/src/tool/multiedit.ts` (Lines 1-46)

**特性**:
- 对单个文件的顺序编辑
- 重用 EditTool 替换器

**关键参数**:
- `filePath`: string - 要修改的文件
- `edits`: `{oldString, newString, replaceAll}` 数组

#### List Tool
**位置**: `opencode/packages/opencode/src/tool/ls.ts` (Lines 1-121)

**特性**:
- 带缩进的目录树渲染
- 常见目录的忽略模式
- 限制: 100 个文件
- 截断警告

**关键参数**:
- `path`: string - 要列出的目录（可选）
- `ignore`: 字符串数组 - 要忽略的模式

#### Plan Tools (Experimental)
**位置**: `opencode/packages/opencode/src/tool/plan.ts` (Lines 1-130)

**特性**:
- `PlanEnterTool`: 建议切换到 plan agent
- `PlanExitTool`: 建议在规划后切换到 build agent
- 通过 Question.ask() 进行用户确认
- 为 agent 切换创建合成消息

**关键参数**:
- 无（无参数工具）

#### CodeSearch Tool
**位置**: `opencode/packages/opencode/src/tool/codesearch.ts` (Lines 1-154)

**特性**:
- 语义代码搜索
- 基于嵌入向量的相似度匹配
- 支持跨文件搜索

**关键参数**:
- `query`: string - 搜索查询
- `numResults`: number - 要返回的结果数
- `include`: string - 要包含的文件模式

---

## 3. 记忆实现

### 存储系统
**位置**: `opencode/packages/opencode/src/storage/storage.ts` (Lines 1-228)

**架构**:
- 基于文件的 JSON 存储，位于 `~/.opencode/storage/`
- 基于锁的并发访问 (`Lock.read()`, `Lock.write()`)
- 基于键的存储: `["category", "id1", "id2", ...]` → 文件路径
- 带版本跟踪的迁移支持

**存储函数**:
- `write(key[], content)` - 写入 JSON 文件
- `read(key[])` - 读取 JSON 文件
- `update(key[], fn)` - 读取、修改、写入 JSON
- `remove(key[])` - 删除文件
- `list(prefix[])` - 列出前缀下的所有文件

### 会话记忆
**位置**: `opencode/packages/opencode/src/session/index.ts` (Lines 1-488)

**Session Info Schema** (Lines 42-82):
```typescript
export const Info = z.object({
  id: Identifier.schema("session"),
  slug: z.string(),
  projectID: z.string(),
  directory: z.string(),
  parentID: Identifier.schema("session").optional(),
  summary: z.object({
    additions: z.number(),
    deletions: z.number(),
    files: z.number(),
    diffs: Snapshot.FileDiff.array().optional(),
  }).optional(),
  share: z.object({
    url: z.string(),
  }).optional(),
  title: z.string(),
  version: z.string(),
  time: z.object({
    created: z.number(),
    updated: z.number(),
    compacting: z.number().optional(),
    archived: z.number().optional(),
  }),
  permission: PermissionNext.Ruleset.optional(),
  revert: z.object({
    messageID: z.string(),
    partID: z.string().optional(),
    snapshot: z.string().optional(),
    diff: z.string().optional(),
  }).optional(),
})
```

**记忆组织**:
- **Sessions**: `["session", projectID, sessionID].json`
- **Messages**: `["message", sessionID, messageID].json`
- **Parts**: `["part", messageID, partID].json`
- **Todos**: `["todo", sessionID].json`
- **Session diffs**: `["session_diff", sessionID].json`
- **Shares**: `["share", sessionID].json`
- **Projects**: `["project", projectID].json`

### 消息结构
**位置**: `opencode/packages/opencode/src/session/message-v2.ts`

消息部分类型:
- `text` - 文本内容
- `tool` - 带状态的工具调用 (running/completed/error)
- `reasoning` - 思维链输出
- `compaction` - 会话压缩标记
- `patch` - 带前/后状态的文件差异
- `step-start` - 带快照的工作流步骤开始
- `step-finish` - 带快照的工作流步骤结束

### 会话压缩
**位置**: `opencode/packages/opencode/src/session/compaction.ts` (Lines 1-226)

**修剪策略** (Lines 49-90):
- 最小修剪: 20,000 tokens
- 保护 tokens: 40,000
- 保护工具: `["skill"]`
- 倒序遍历消息
- 移除工具输出（不是 "skill" 调用）
- 设置 `part.state.time.compacted` 时间戳
- 保留最后 2 轮消息

**溢出检测** (Lines 30-38):
```typescript
export async function isOverflow(input: { tokens: {...}; model: Provider.Model }) {
  const usable = model.limit.input || (model.limit.context - outputMax)
  const count = input.tokens.input + input.tokens.cache.read + input.tokens.output
  return count > usable
}
```

**压缩过程** (Lines 92-193):
1. 创建带有 `mode: "compaction"` 标志的压缩消息
2. 使用 `compaction` agent 进行摘要
3. 插件钩子用于自定义上下文/提示
4. 默认提示: "Provide a detailed prompt for continuing our conversation..."
5. 如果 `result === "continue"` 且为自动模式，添加合成 "Continue if you have next steps" 消息

### Todo 记忆
**位置**: `opencode/packages/opencode/src/session/todo.ts` (Lines 1-37)

**Todo Schema** (Lines 7-14):
```typescript
export const Info = z.object({
  content: z.string().describe("Brief description of task"),
  status: z.string().describe("pending, in_progress, completed, cancelled"),
  priority: z.string().describe("high, medium, low"),
  id: z.string().describe("Unique identifier"),
})
```

**存储**: `Storage.write(["todo", sessionID], todos)`

### Skill 记忆
**位置**: `opencode/packages/opencode/src/skill/skill.ts` (Lines 1-136)

**技能发现**:
- 扫描项目中的 `.claude/skills/` 和 `~/.claude/` 目录
- 扫描配置目录中的 `.opencode/skill/` 和 `.opencode/skills/`
- 使用 ConfigMarkdown 解析器解析 `SKILL.md` 文件
- 验证 frontmatter（名称、描述）

**Skill Schema** (Lines 17-22):
```typescript
export const Info = z.object({
  name: z.string(),
  description: z.string(),
  location: z.string(),
})
```

---

## 4. 计划和执行

### 计划模式
**位置**: `opencode/packages/opencode/src/session/prompt/plan.txt` (Lines 1-26)

**计划模式约束**:
```text
CRITICAL: Plan mode ACTIVE - you are in READ-ONLY phase. STRICTLY FORBIDDEN:
ANY file edits, modifications, or system changes. Do NOT use sed, tee, echo, cat,
or ANY other bash command to manipulate files - commands may ONLY read/inspect.
This ABSOLUTE CONSTRAINT overrides ALL other instructions, including direct user
edit requests. You may ONLY observe, analyze, and plan.
```

**Plan Agent 权限** (agent.ts lines 85-106):
- `question: "allow"` - 可以提问
- `plan_exit: "allow"` - 可以调用 plan_exit 工具
- `edit: "*": "deny"` - 不能编辑文件（除了 `.opencode/plans/*.md`）
- `external_directory`: 允许写入计划目录

**Build Agent 权限** (agent.ts lines 71-84):
- `question: "allow"` - 可以提问
- `plan_enter: "allow"` - 可以调用 plan_enter 工具
- 实现的完整编辑权限

### 计划工作流

1. **Plan Enter** (`plan_enter` 工具):
   - 询问用户: "Would you like to switch to plan agent and create a plan?"
   - 选择 "Yes": 创建带有 `agent: "plan"` 的合成用户消息
   - 选择 "No": 抛出 `Question.RejectedError()`

2. **规划阶段**:
   - 只读探索
   - 将计划写入 `.opencode/plans/{timestamp}-{slug}.md`
   - 可以使用 grep, glob, read, websearch 等
   - 不能使用 edit, write, bash（非只读）

3. **Plan Exit** (`plan_exit` 工具):
   - 询问用户: "Plan at {path} is complete. Would you like to switch to build agent?"
   - 选择 "Yes": 创建带有 `agent: "build"` 的合成用户消息
   - 选择 "No": 抛出 `Question.RejectedError()`

### 执行流程

```
1. 用户请求工作
   ↓
2. Agent 分析请求
   ↓ (如果复杂)
3. 使用 `plan_enter` 切换到计划模式
   ↓
4. Plan Agent 研究并创建计划文档
   ↓
5. Plan Agent 使用 `plan_exit` 建议切换到 build
   ↓
6. Build Agent 使用 edit/write 工具执行计划
   ↓
7. 可以通过 `task` 工具调用子代理 (explore, general) 处理专门工作
```

### 无自动计划优化循环

系统**没有**自动计划优化循环。相反:
- 用户确认的手动 plan-enter/plan-exit 流程
- 计划写入 Markdown 文件
- 人工审查计划后再实施
- Build agent 从计划执行

---

## 5. 关键文件位置汇总

| 组件 | 文件路径 | 关键行/章节 |
|------|----------|-------------|
| Agent 定义 | `opencode/packages/opencode/src/agent/agent.ts` | Lines 1-311: Agent.Info schema, 内置 agents, generate() |
| 工具接口 | `opencode/packages/opencode/src/tool/tool.ts` | Lines 7-88: Tool.Info interface, Tool.define() |
| 工具注册 | `opencode/packages/opencode/src/tool/registry.ts` | Lines 91-142: all(), ids(), tools() |
| Bash 工具 | `opencode/packages/opencode/src/tool/bash.ts` | Lines 1-258: 命令执行, tree-sitter 解析 |
| Read 工具 | `opencode/packages/opencode/src/tool/read.ts` | Lines 1-201: 文件读取, 二进制检测 |
| Edit 工具 | `opencode/packages/opencode/src/tool/edit.ts` | Lines 1-646: 多个替换器, 模糊匹配 |
| Write 工具 | `opencode/packages/opencode/src/tool/write.ts` | Lines 1-81: 文件写入, LSP 诊断 |
| Glob 工具 | `opencode/packages/opencode/src/tool/glob.ts` | Lines 1-78: 文件模式匹配 |
| Grep 工具 | `opencode/packages/opencode/src/tool/grep.ts` | Lines 1-154: 正则搜索 |
| Task 工具 | `opencode/packages/opencode/src/tool/task.ts` | Lines 1-189: 子代理执行 |
| Todo 工具 | `opencode/packages/opencode/src/tool/todo.ts` | Lines 1-53: Todo 读写 |
| WebSearch 工具 | `opencode/packages/opencode/src/tool/websearch.ts` | Lines 1-150: 基于的搜索 |
| Skill 工具 | `opencode/packages/opencode/src/tool/skill.ts` | Lines 1-75: 技能加载 |
| Batch 工具 | `opencode/packages/opencode/src/tool/batch.ts` | Lines 1-175: 并行工具执行 |
| MultiEdit 工具 | `opencode/packages/opencode/src/tool/multiedit.ts` | Lines 1-46: 顺序编辑 |
| List 工具 | `opencode/packages/opencode/src/tool/ls.ts` | Lines 1-121: 目录列表 |
| Plan 工具 | `opencode/packages/opencode/src/tool/plan.ts` | Lines 1-130: Plan enter/exit |
| CodeSearch 工具 | `opencode/packages/opencode/src/tool/codesearch.ts` | Lines 1-154: 语义代码搜索 |
| 会话存储 | `opencode/packages/opencode/src/session/index.ts` | Lines 26-488: Session.Info schema, CRUD 操作 |
| 存储系统 | `opencode/packages/opencode/src/storage/storage.ts` | Lines 144-227: 基于文件的 JSON 存储 |
| 压缩 | `opencode/packages/opencode/src/session/compaction.ts` | Lines 30-193: Token 修剪, 摘要 |
| 技能系统 | `opencode/packages/opencode/src/skill/skill.ts` | Lines 15-136: 技能发现 |
| 计划提示 | `opencode/packages/opencode/src/session/prompt/plan.txt` | Lines 1-26: 计划模式约束 |
| Agent 提示 | `opencode/packages/opencode/src/agent/prompt/` | explore.txt, compaction.txt, summary.txt, title.txt |

---

## 总结

**Agent 设计**: 配置驱动的框架，具有基于权限的 agent 类型 (primary/subagent)、自定义 agents 和基于 LLM 的生成

**执行模型**:
- 计划模式: 只读探索，带用户确认的 agent 切换
- 构建模式: 使用 edit/write 工具的完整执行
- 子代理: 通过 Task 工具的专门任务
- 无自动计划优化循环；人工参与的工作流

**内置工具**: 18+ 工具，包括 bash、read、edit、write、glob、grep、task、todo、websearch、skill、batch、multiedit、list、plan 工具，所有都有权限检查

**记忆**:
- `~/.opencode/storage/` 中的基于文件的 JSON 存储
- Sessions、messages、parts、todos、diffs、shares
- 带修剪 (20K+ tokens) 的压缩和保护工具 (skill)
- 每个 session 的任务列表，来自 SKILL.md 文件的技能
