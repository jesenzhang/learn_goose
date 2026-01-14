# Artifact Manager 集成指南

## 问题分析

当前 `shared_memory` 存储机制存在以下问题：

| 问题 | 现状 | 影响 |
|------|------|------|
| 无限增长 | Artifact 数据只增不减 | 长对话内存暴增 |
| 序列化开销 | 每次 `save_state` 都要 JSON 序列化 | 性能下降 |
| 数据库膨胀 | 所有数据存 SQLite TEXT 字段 | DB 文件过大 |
| 无清理机制 | 旧的 artifact 永远保留 | 浪费资源 |

## 解决方案：ArtifactManager

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        shared_memory                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  art_abc123: {                                        │  │
│  │    id: "art_abc123",                                   │  │
│  │    type: "dataset",                                    │  │
│  │    text: "推荐结果: 三彩",                              │  │
│  │    size: 2048,           # 仅引用，不包含实际数据      │  │
│  │    storage: "memory",     # 存储位置                    │  │
│  │    created_at: 1234567890                              │  │
│  │  }                                                     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      ArtifactManager                          │
│  ┌─────────────┬──────────────────┬──────────────────────┐  │
│  │   Memory    │    Compressed    │       File           │  │
│  │  (<10KB)    │    (10-100KB)    │     (>100KB)         │  │
│  │             │                  │                      │  │
│  │  完整数据    │   gzip压缩数据   │   artifacts/         │  │
│  │             │                  │   {session_id}/      │  │
│  │             │                  │   artifact_xxx.json  │  │
│  └─────────────┴──────────────────┴──────────────────────┘  │
│                                                             │
│  LRU 管理:                                                 │
│  - MAX_MEMORY_ITEMS: 50                                    │
│  - MAX_TOTAL_MEMORY: 50MB                                  │
│  - ARTIFACT_TTL: 24小时                                    │
└─────────────────────────────────────────────────────────────┘
```

### 存储策略

| 数据大小 | 存储方式 | 优点 | 适用场景 |
|---------|---------|------|---------|
| < 10KB | 直接内存 | 快速访问 | FAQ 响应、小列表 |
| 10-100KB | gzip 压缩 | 节省内存 | 中等搜索结果 |
| > 100KB | 临时文件 | 内存可控 | 大型数据集、图表数据 |

### 集成到 MicroAgent

#### 1. 在 `__init__` 中初始化

```python
# agent.py

from .artifact_manager import ArtifactManager, ArtifactRef

class MicroAgent:
    def __init__(self, config_path: str):
        # ... 现有初始化代码 ...

        # Artifact Manager (会话级别管理器)
        self._artifact_managers: Dict[str, ArtifactManager] = {}
```

#### 2. 获取/创建会话的 ArtifactManager

```python
def _get_artifact_manager(self, session_id: str) -> ArtifactManager:
    """获取或创建会话的 ArtifactManager"""
    if session_id not in self._artifact_managers:
        self._artifact_managers[session_id] = ArtifactManager(
            session_id=session_id,
            base_dir="artifacts"  # 可配置
        )
    return self._artifact_managers[session_id]
```

#### 3. 修改 `_format_and_emit_tool_result` 方法

```python
async def _format_and_emit_tool_result(
    self,
    result: CallToolResult,
    state: AgentState
) -> str:
    """格式化工具结果并发送 artifact 事件"""
    artifact_mgr = self._get_artifact_manager(state.session_id)

    parts = []
    for c in result.content:
        # 如果包含结构化数据 (Artifact)
        if c.data is not None:
            # 1. 生成唯一的 Artifact ID
            aid = f"art_{uuid.uuid4().hex[:8]}"

            # 2. 存储到 ArtifactManager (自动选择存储方式)
            ref = artifact_mgr.store(
                aid=aid,
                artifact_type=c.type or "dataset",
                data=c.data,
                text=c.text or ""
            )

            # 3. 存储引用到 shared_memory (轻量级)
            state.shared_memory[aid] = ref.model_dump()

            # 4. 触发 Artifact 事件 (前端渲染)
            await self.events.emit(EventType.TOOL_ARTIFACT, {
                "id": aid,
                "type": ref.type,
                "text": ref.text,
                # 注意：不再发送完整 data，前端需要时通过 API 获取
            })

            # 5. 返回给 LLM 的只是一个引用
            parts.append(f"{c.text or 'Generated Data'}\n[Artifact ID: {aid}]")
        else:
            parts.append(c.text or "")

    return "\n\n".join(parts)
```

#### 4. 添加获取 Artifact 的 API 端点

```python
async def get_artifact(self, session_id: str, artifact_id: str) -> Optional[Dict]:
    """
    获取 artifact 数据（供前端 API 调用）

    前端流程：
    1. 收到 TOOL_ARTIFACT 事件（包含 id）
    2. 调用 GET /api/artifacts/{session_id}/{artifact_id}
    3. 渲染数据
    """
    artifact_mgr = self._get_artifact_manager(session_id)
    data = artifact_mgr.load(artifact_id)

    if data is None:
        return None

    return {
        "id": artifact_id,
        "data": data
    }
```

#### 5. 修改 `_emit_tool_artifacts` 方法

```python
async def _emit_tool_artifacts(self, result: CallToolResult, state: AgentState) -> None:
    """只触发 TOOL_ARTIFACT 事件，不返回文本（用于 Hook 拦截场景）"""
    artifact_mgr = self._get_artifact_manager(state.session_id)

    for c in result.content:
        if c.data is not None:
            aid = f"art_{uuid.uuid4().hex[:8]}"

            # 使用 ArtifactManager 存储
            ref = artifact_mgr.store(
                aid=aid,
                artifact_type=c.type or "dataset",
                data=c.data,
                text=c.text or ""
            )

            # 存储引用
            state.shared_memory[aid] = ref.model_dump()

            # 触发事件
            await self.events.emit(EventType.TOOL_ARTIFACT, {
                "id": aid,
                "type": ref.type,
                "text": ref.text
            })
```

#### 6. 会话结束时清理

```python
async def close_session(self, session_id: str):
    """清理会话资源"""
    # 清理 artifacts
    if session_id in self._artifact_managers:
        count = self._artifact_managers[session_id].cleanup_all()
        logger.info(f"Cleaned up {count} artifacts for session {session_id}")
        del self._artifact_managers[session_id]

    # 清理数据库状态（可选）
    # await self.db.delete_session(session_id)
```

### API 端点修改（FastAPI 示例）

```python
# api/routes.py

from fastapi import HTTPException

@router.get("/sessions/{session_id}/artifacts/{artifact_id}")
async def get_artifact(session_id: str, artifact_id: str):
    """获取 artifact 数据"""
    # 获取 agent 实例 (根据你的架构调整)
    agent = get_agent_instance()

    result = await agent.get_artifact(session_id, artifact_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return result

@router.get("/sessions/{session_id}/artifacts/stats")
async def get_artifact_stats(session_id: str):
    """获取 artifact 统计信息（调试用）"""
    agent = get_agent_instance()
    mgr = agent._get_artifact_manager(session_id)
    return mgr.get_stats()
```

### 优势总结

| 方面 | 原方案 | ArtifactManager |
|------|--------|-----------------|
| 内存占用 | 无限增长 | LRU 限制 + 分层存储 |
| 序列化 | 每次 dump 全量 JSON | 只序列化轻量引用 |
| 数据库大小 | 随对话线性增长 | 恒定大小 (只存引用) |
| 持久化 | SQLite | 内存/文件混合 |
| 清理 | 手动 | 自动 (LRU + TTL) |
| 并发性能 | 锁竞争 | 文件隔离 |

### 配置参数

```python
# artifact_manager.py

class ArtifactManager:
    # 可根据实际情况调整
    SMALL_SIZE_LIMIT = 10 * 1024      # 10KB - 直接内存
    LARGE_SIZE_LIMIT = 100 * 1024     # 100KB - 文件存储

    MAX_MEMORY_ITEMS = 50             # 最多保留 50 个
    MAX_TOTAL_MEMORY = 50 * 1024 * 1024  # 总内存 50MB

    ARTIFACT_TTL = 86400              # 24小时后清理
```

### 迁移步骤

1. **创建 ArtifactManager 类** ✅ (已创建)

2. **修改 Agent 类**:
   - 添加 `_artifact_managers` 字典
   - 添加 `_get_artifact_manager` 方法
   - 修改 `_format_and_emit_tool_result`
   - 修改 `_emit_tool_artifacts`
   - 添加 `get_artifact` 方法
   - 添加 `close_session` 方法

3. **修改 API 端点**:
   - 添加 `GET /api/artifacts/{session_id}/{artifact_id}`
   - 前端改为先收到事件，再调用 API 获取数据

4. **测试**:
   - 验证大数据场景
   - 验证长对话内存控制
   - 验证清理机制

### 兼容性考虑

如果需要兼容旧数据：

```python
def _load_legacy_artifact(self, state: AgentState, aid: str) -> Optional[Any]:
    """加载旧格式 artifact (迁移期使用)"""
    if aid in state.shared_memory:
        data = state.shared_memory[aid]
        # 检查是否是旧格式（包含完整 data）
        if isinstance(data, dict) and "data" in data and "id" in data:
            if "storage" not in data:  # 旧格式
                # 迁移到新格式
                mgr = self._get_artifact_manager(state.session_id)
                ref = mgr.store(
                    aid=aid,
                    artifact_type=data.get("type", "dataset"),
                    data=data["data"],
                    text=data.get("text", "")
                )
                # 更新 shared_memory
                state.shared_memory[aid] = ref.model_dump()
                return data["data"]

    return None
```
