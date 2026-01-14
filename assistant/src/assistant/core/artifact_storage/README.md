# Artifact Storage Module

可插拔的 artifact 存储后端管理系统。

## 特性

- **可插拔架构** - 支持多种存储后端，易于扩展
- **配置驱动** - YAML 配置文件，支持环境变量覆盖
- **自动清理** - LRU 淘汰 + TTL 过期清理
- **会话隔离** - 不同会话的数据完全隔离
- **性能优化** - 分层存储策略，小数据内存，大数据文件
- **线程安全** - 支持并发访问（通过锁或连接池）

## 存储后端

| 存储类型 | 特性 | 适用场景 |
|---------|------|---------|
| `memory` | LRU 缓存，快速访问 | 小数据、频繁访问、测试环境 |
| `file` | JSON 文件，持久存储 | 大型数据集、需持久化 |
| `hybrid` | 混合策略（自动选择） | 生产环境、混合数据 |
| `database` | SQLite，事务安全 | 生产环境、高并发 |

## 快速开始

### 基本使用

```python
from assistant.core.artifact_storage import init_manager

# 初始化（在 agent 启动时调用）
init_manager(config_path="artifact_manager_config.yaml")

# 获取管理器
artifact_mgr = get_manager()

# 存储 artifact
ref = await artifact_mgr.store(
    session_id="session_123",
    artifact_id="art_abc123",
    artifact_type="dataset",
    data=my_data,
    text="推荐结果"
)

# 加载 artifact
data = await artifact_mgr.load(
    session_id="session_123",
    artifact_id="art_abc123"
)

# 删除 artifact
await artifact_mgr.delete(
    session_id="session_123",
    artifact_id="art_abc123"
)

# 清理会话
await artifact_mgr.cleanup_session(session_id="session_123")
```

### 自定义存储后端

```python
from assistant.core.artifact_storage import register_storage, ArtifactStorage, StorageConfig, ArtifactRef, StorageType

@register_storage(StorageType.CUSTOM, MyStorageConfig)
class MyStorage(ArtifactStorage):
    def __init__(self, config: MyStorageConfig, session_id: str):
        super().__init__(config, session_id)

    async def store(self, ref: ArtifactRef, data: Any) -> ArtifactRef:
        # 实现存储逻辑
        pass

    async def load(self, ref: ArtifactRef) -> Optional[Any]:
        # 实现加载逻辑
        pass

    # ... 实现其他方法
```

### 配置文件

配置文件优先级（从高到低）：
1. 环境变量 `ARTIFACT_MANAGER_OVERRIDE`
2. `artifact_manager_config.yaml`（独立文件）
3. `assistant_config.yaml` 中的 `artifact_manager` 部分

## API 设计

### 前端事件流

```
┌─────────────────────────────────────────────────────┐
│ Frontend                                       │
│  1. 收到 TOOL_ARTIFACT 事件                    │
│    {id: "art_abc123", type: "dataset", text: "..."}  │
│                                                 │
│ 2. 需要完整数据时                              │
│    GET /api/sessions/{session_id}/artifacts/{artifact_id} │
│    {id: "art_abc123", data: {...}}               │
└─────────────────────────────────────────────────────┘
```

## 设计模式

### Registry Pattern

存储后端注册中心，支持装饰器注册：

```python
@register_storage(StorageType.MY_TYPE)
class MyStorage(ArtifactStorage):
    ...
```

### Factory Pattern

根据配置创建存储后端：

```python
storage = registry.create(config, session_id)
```

### Adapter Pattern

统一接口，不同实现：

```python
class ArtifactStorage(ABC):
    @abstractmethod
    async def store(self, ref, data) -> ArtifactRef:
        pass
```

### Repository Pattern

数据访问层抽象：

```python
await storage.load(ref)
await storage.delete(ref)
await storage.cleanup_old()
```

## 性能考虑

| 操作 | Memory | File | Hybrid | Database |
|------|--------|------|--------|----------|
| 存储 | O(1) | O(1) + I/O | O(1) | O(log n) |
| 加载 | O(1) | O(1) + I/O | O(1) | O(log n) |
| 删除 | O(1) | O(1) + I/O | O(1) | O(log n) |
| 清理 | O(n) | O(n) + I/O | O(n) | O(n) |
| 内存占用 | 高 | 低 | 中 | 最低 |

## 故障处理

```python
# 存储后端异常处理
try:
    ref = await storage.store(ref, data)
except Exception as e:
    logger.error(f"Storage failed: {e}")
    # 回退到备用存储或返回错误

# 优雅降级
if primary_storage is None:
    fallback_storage = get_fallback_storage()
```

## 监控

```python
# 获取统计信息
stats = await artifact_mgr.get_stats(session_id="session_123")
print(f"Total: {stats['total_count']}, Size: {stats['total_size']}")

# 健康检查
health = await artifact_mgr.health_check()
```

## 参考实现

本模块设计参考了以下项目的模式：

1. **goose-rs** - SessionStorage（SQLite + 连接池）
2. **goose-rs** - AnalysisCache（LRU 缓存）
3. **goose-py** - ToolRegistry（注册中心）
4. **skill_micro_agent** - SkillLoader（目录扫描 + 配置加载）
5. **goose-rs** - ProviderRegistry（工厂模式）

## 文件说明

- `base.py` - 抽象基类和接口定义
- `registry.py` - 存储后端注册中心
- `config.py` - 配置加载和验证
- `manager.py` - 统一管理器，集成多个后端
- `memory.py` - 内存存储实现（LRU）
- `file.py` - 文件存储实现（JSON + 可选压缩）
- `hybrid.py` - 混合存储实现（自动分层）
- `database.py` - SQLite 存储实现
