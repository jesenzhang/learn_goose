# Artifact Storage 模块集成指南

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                     MicroAgent                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         ArtifactManager                           │   │
│  │  ┌────────────────────────────────────────────────────┐   │   │
│  │  │     ArtifactStorageRegistry                 │   │   │
│  │  │  MemoryStorage │ FileStorage │ Database │   │   │
│  │  │  (LRU)      │ (JSON)       │ (SQL)   │   │
│  │  └────────────────────────────────────────────────────┘   │   │
│  │                                                     │   │
│  │  配置源                                            │   │
│  │  ┌──────────────────────────────────────────────────┐      │   │
│  │  │ 1. artifact_manager_config.yaml (主）   │      │   │
│  │  │ 2. assistant_config.yaml (集成）         │      │   │
│  │  │ 3. 环境变量 ARTIFACT_MANAGER_OVERRIDE │      │   │
│  │  └──────────────────────────────────────────────────┘      │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                            │
│  shared_memory                                               │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  art_abc123: {ArtifactRef} (轻量级）     │   │
│  │  art_def456: {ArtifactRef} (轻量级）     │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## 文件结构

```
assistant/
└── src/
    └── assistant/
        ├── core/
        │   ├── agent.py                     # MicroAgent 主类
        │   ├── artifact_storage/
        │   │   ├── __init__.py             # 模块入口
        │   │   ├── base.py                 # 抽象基类
        │   │   ├── registry.py             # 存储后端注册
        │   │   ├── config.py               # 配置加载
        │   │   ├── manager.py              # 统一管理器
        │   │   ├── memory.py               # 内存存储
        │   │   ├── file.py                 # 文件存储
        │   │   ├── hybrid.py               # 混合存储
        │   │   └── database.py             # 数据库存储
        │   └── ...
        ├── config/
        │   └── assistant_config.yaml       # 集成配置
        └── ...
artifact_manager_config.yaml                  # 独立配置文件
artifacts/                                  # 文件存储基础目录
    ├── {session_id}/
    │   ├── artifact_xxx.json
    │   └── artifact_xxx.json.gz
    └── ...
```

## 集成步骤

### 1. 修改 MicroAgent 类

```python
# assistant/core/agent.py

from .artifact_storage import init_manager, get_manager

class MicroAgent:
    def __init__(self, config_path: str):
        # ... 现有初始化代码 ...

        # 初始化 ArtifactManager
        init_manager(config_path=config_path)

    async def process_request(self, ...):
        # ... 现有代码 ...

        # 替换原来的 _format_and_emit_tool_result
        await self._emit_artifact_with_manager(result, state)
```

### 2. 实现 _emit_artifact_with_manager

```python
async def _emit_artifact_with_manager(
    self,
    result: CallToolResult,
    state: AgentState
) -> str:
    """使用 ArtifactManager 存储和发送 artifact 事件"""
    artifact_mgr = get_manager()

    if artifact_mgr is None or not artifact_mgr.config.enabled:
        # 回退到原始实现
        return await self._format_and_emit_tool_result_original(result, state)

    parts = []
    for c in result.content:
        if c.data is not None:
            # 生成唯一的 Artifact ID
            aid = f"art_{uuid.uuid4().hex[:8]}"

            # 使用 ArtifactManager 存储
            ref = await artifact_mgr.store(
                session_id=state.session_id,
                artifact_id=aid,
                artifact_type=c.type or "dataset",
                data=c.data,
                text=c.text or "",
            )

            # 存储引用到 shared_memory（轻量级）
            state.shared_memory[aid] = ref.to_dict()

            # 触发 TOOL_ARTIFACT 事件
            await self.events.emit(EventType.TOOL_ARTIFACT, {
                "id": aid,
                "type": ref.type,
                "text": ref.text,
            })

            # 返回给 LLM 的只是一个引用
            parts.append(f"{c.text or 'Generated Data'}\n[Artifact ID: {aid}]")
        else:
            parts.append(c.text or "")

    return "\n\n".join(parts)
```

### 3. 添加 API 端点

```python
# assistant/api/routes.py

from fastapi import HTTPException
from .artifact_storage import get_manager

@router.get("/sessions/{session_id}/artifacts/{artifact_id}")
async def get_artifact(session_id: str, artifact_id: str):
    """获取 artifact 数据"""
    artifact_mgr = get_manager()
    if artifact_mgr is None:
        raise HTTPException(status_code=503, detail="Artifact manager not available")

    data = await artifact_mgr.load(
        session_id=session_id,
        artifact_id=artifact_id,
    )

    if data is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return {
        "id": artifact_id,
        "data": data,
    }

@router.get("/sessions/{session_id}/artifacts")
async def list_artifacts(session_id: str):
    """列出会话的所有 artifacts"""
    artifact_mgr = get_manager()
    if artifact_mgr is None:
        raise HTTPException(status_code=503, detail="Artifact manager not available")

    refs = await artifact_mgr.list_all(session_id=session_id)

    return {
        "session_id": session_id,
        "artifacts": [
            {
                "id": ref.id,
                "type": ref.type,
                "text": ref.text,
                "size": ref.size,
                "created_at": ref.created_at,
            }
            for ref in refs
        ],
    }

@router.delete("/sessions/{session_id}/artifacts/{artifact_id}")
async def delete_artifact(session_id: str, artifact_id: str):
    """删除 artifact"""
    artifact_mgr = get_manager()
    if artifact_mgr is None:
        raise HTTPException(status_code=503, detail="Artifact manager not available")

    success = await artifact_mgr.delete(
        session_id=session_id,
        artifact_id=artifact_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return {"deleted": artifact_id}

@router.delete("/sessions/{session_id}")
async def cleanup_session(session_id: str):
    """清理会话的所有 artifacts"""
    artifact_mgr = get_manager()
    if artifact_mgr is None:
        raise HTTPException(status_code=503, detail="Artifact manager not available")

    count = await artifact_mgr.cleanup_session(session_id=session_id)
    return {"cleaned": count}
```

### 4. 会话结束时清理

```python
# assistant/core/agent.py

async def end_session(self, session_id: str):
    """结束会话时清理资源"""
    artifact_mgr = get_manager()
    if artifact_mgr:
        await artifact_mgr.cleanup_session(session_id=session_id)

    # ... 其他清理逻辑 ...
```

### 5. 集成到 assistant_config.yaml

```yaml
# assistant/config/assistant_config.yaml

# Artifact Manager 配置
artifact_manager:
  enabled: true
  default_storage: hybrid          # memory, file, hybrid, database

  # 全局清理配置
  cleanup_interval: 3600         # 1 小时
  ttl: 86400                   # 24 小时

  # 会话级别限制
  max_items_per_session: 50
  max_bytes_per_session: 52428800  # 50MB

  # 各存储类型的特定配置
  storage_configs:
    memory:
      max_items: 50
      max_size_bytes: 52428800
      ttl: 3600                  # 1 小时

    file:
      base_dir: artifacts
      compression: false
      ttl: 86400

    hybrid:
      memory_threshold: 10240      # 10KB
      file_threshold: 102400      # 100KB
      compression: true
      max_items: 100
      max_size_bytes: 104857600  # 100MB

    database:
      table_name: artifacts
      ttl: 86400
```

### 6. 独立配置文件（可选）

```yaml
# artifact_manager_config.yaml

artifact_manager:
  enabled: true
  default_storage: hybrid

  storage_configs:
    hybrid:
      memory_threshold: 10240      # 10KB
      file_threshold: 102400      # 100KB
      compression: true
```

### 7. 环境变量覆盖

```bash
# 覆盖整个配置
export ARTIFACT_MANAGER_OVERRIDE='enabled: true; default_storage: memory'

# Windows PowerShell
$env:ARTIFACT_MANAGER_OVERRIDE="enabled: true; default_storage: memory"
```

## 存储后端对比

| 特性 | Memory | File | Hybrid | Database |
|------|--------|------|--------|----------|
| 访问速度 | ⚡ 最快 | 🐌 慢 | ⚡ 快 | 🐌 中等 |
| 内存占用 | 🔴 高 | 🟢 低 | 🟡 中 | 🟢 最低 |
| 持久化 | ❌ 无 | ✅ 有 | ✅ 有 | ✅ 有 |
| 进程重启后 | ❌ 丢失 | ✅ 保留 | ✅ 保留 | ✅ 保留 |
| LRU 淘汰 | ✅ 有 | ❌ 无 | ✅ 有 | ⚡ 手动 |
| 自动清理 | ✅ 有 | ⚡ 手动 | ✅ 有 | ⚡ 手动 |
| 适用场景 | 小数据 | 大数据 | 混合需求 | 生产环境 |

## 设计模式说明

### 1. Registry Pattern

```python
# 注册存储后端
@register_storage(StorageType.MEMORY)
class MemoryStorage(ArtifactStorage):
    ...
```

### 2. Factory Pattern

```python
# 配置驱动的创建
storage = registry.create(config, session_id)
```

### 3. Template Method Pattern

```python
# 基类定义模板，子类实现具体方法
class ArtifactStorage(ABC):
    @abstractmethod
    async def store(self, ref, data) -> ArtifactRef:
        pass
```

### 4. Builder Pattern (配置验证)

```python
# Pydantic 模型自动验证
config = ArtifactStorageConfigModel(**config_data)
```

## 迁移策略

### 阶段 1：兼容模式

```python
# 旧数据保持用 shared_memory 直接存储
async def _emit_artifact_with_manager(...):
    if _has_legacy_data(state):
        # 保持旧方式
        return await _legacy_emit(result, state)
    else:
        # 使用新方式
        return await _new_emit(result, state)
```

### 阶段 2：逐步迁移

```python
# 新数据使用 ArtifactManager
async def store_new_artifact(...):
    ref = await artifact_mgr.store(...)
```

### 阶段 3：完全切换

```python
# 所有数据使用 ArtifactManager
async def store_artifact(...):
    ref = await artifact_mgr.store(...)
```

## 测试清单

- [ ] 单元测试（各存储后端）
- [ ] 集成测试（ArtifactManager + MicroAgent）
- [ ] 性能测试（大量 artifact 存储）
- [ ] 长时间运行测试（内存泄漏）
- [ ] 并发测试（多请求同时访问）
- [ ] 配置热重载测试
- [ ] 清理机制测试（LRU、TTL）
