# Context 模块全量重构与统一计划

## Summary
目标是把“上下文处理”作为独立核心模块，统一承载：长输入分段、需求抽取、上下文压缩、预算管理、召回/重写、窗口策略、缓存与指标。该计划以分阶段落地，优先保证现有逻辑稳定可用，再逐步接入全量能力。

---

## 目标与边界
**目标**
- Context 成为单一“上下文处理引擎”，对外提供统一入口（`ContextManager`）
- 完整覆盖：  
  - 长输入分段与需求抽取（启发式 + LLM 分类器）  
  - 结构化摘要与压缩（结构模板）  
  - Token 预算统一器（ContextBudget）  
  - 历史窗口管理（最近 N / boundary）  
  - ChatRecall + QueryRewrite 迁入 Context  
  - 语义检索与 rerank 流程（Provider 注入）  
  - 召回摘要合成  
  - 缓存层与指标输出  
  - 日志与诊断能力  

**不在此阶段内**
- 不改动 memory 模块的底层存储实现  
- 不改动 provider SDK 和网络层实现  

---

## Public APIs / Interfaces
### 1) ContextManager API
- `analyze_input(input_text, max_tokens) -> ContextAnalysis`
- `build_context(state, conv, system_prompt, tools) -> ContextPayload`
- `apply_truncation(conv, system_prompt, tools) -> TruncationResult`
- `recall_and_rewrite(query, history, session_id) -> RecallBundle`

### 2) Provider 协议接口
- `TokenCounter`
- `LLMClient`
- `RecallProvider`
- `RerankProvider`
- `EmbeddingProvider`
- `TruncationProvider`

### 3) Data Models（Context 内）
- `ContextBudget`
- `ContextAnalysis`
- `RequirementExtraction`
- `RecallSummary`
- `RecallBundle`
- `TruncationResult`
- `ContextPayload`

---

## Phase Plan
### Phase 1 — 接口与结构
**交付物**
- `context/PLAN.md`
- 完整数据结构与接口草案

### Phase 2 — 预算器 + Token 分段
**交付物**
- `budget.py`  
- Token-aware 分段  

### Phase 3 — 需求抽取 + 结构化摘要
**交付物**
- 需求分类器（启发式 + LLM）  
- 结构化摘要模板  

### Phase 4 — Recall / Rewrite
**交付物**
- `recall.py`, `rewrite.py`
- ChatRecall 适配  

### Phase 5 — ContextPayload 统一构建
**交付物**
- 统一输入拼装  
- WindowManager 对接  

### Phase 6 — 指标 / 缓存 / 诊断
**交付物**
- `metrics.py`, `cache.py`

### Phase 7 — Agent 全量接入
**交付物**
- Context 完整替换 Agent 内部逻辑  
- 回滚与开关控制  

---

## 测试用例与验收
- 长输入超限不会触发 413/400  
- 需求在开头/结尾可正确抽取  
- LLM 分类器关闭仍可工作  
- recall 为空不影响主流程  
- 压缩后不丢关键事实  

---

## Assumptions & Defaults
- Context 作为唯一输入处理入口  
- recall / rewrite 统一由 Context 承担  
- TokenCounter 使用 rough 估算，后续可替换 tokenizer  
