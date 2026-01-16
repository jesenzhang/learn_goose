# Memory Module 重构升级计划

> **状态**: 已规划，暂未实施
> **创建日期**: 2025-01-17
> **目标**: 将 `artifact_storage` 模块升级为更通用的 `Memory` 模块，实现分层记忆管理

---

## 1. 背景分析

### 1.1 当前实现

**shared_memory (Hot Data Layer)**
- 位置: `AgentState.shared_memory: Dict[str, Any]`
- 用途:
  - Artifact 引用（ArtifactRef 字典）
  - skill_params（skill 参数配置）
  - _restricted_tools（工具限制列表）
  - FAQ 标记（_faq_already_queried）
  - 临时状态、页面内容等
- 特点:
  - ✅ 简单快速 - 直接字典访问
  - ✅ 自动持久化 - 序列化到数据库
  - ✅ 同步 API - 无需 await
  - ❌ 无 LRU 缓存
  - ❌ 无 TTL 过期
  - ❌ 无存储后端抽象

**artifact_storage (Cold Data Layer)**
- 位置: `assistant/src/assistant/core/artifact_storage/`
- 用途:
  - Artifact 实际数据存储
  - 多种存储后端（Memory, File, Hybrid, Database）
- 特点:
  - ✅ LRU 自动淘汰
  - ✅ TTL 过期清理
  - ✅ 可插拔存储后端
  - ✅ 批量操作支持
  - ⚠️ 异步 API（async/await）
  - ⚠️ 相对复杂，需要额外初始化

### 1.2 问题与挑战

1. **命名混淆**: `artifact_storage` 名字过于具体，实际是通用的记忆管理
2. **职责不清**: shared_memory 和 artifact_storage 功能重叠
3. **API 不一致**: 同步 vs 异步，使用体验割裂
4. **过度工程**: 简单配置数据是否需要 LRU/TTL？

---

## 2. 重构方案概述

### 2.1 核心理念

**渐进式重构 + 分层管理**

不破坏现有代码，通过以下方式逐步升级：
- 重命名 `artifact_storage` → `Memory`（更通用）
- 保持 `shared_memory` 作为热数据层
- `Memory` 作为冷数据层
- 通过透明代理实现无感知访问

### 2.2 分层架构

```
┌─────────────────────────────────────────┐
│   shared_memory (Hot Data Layer)       │  ← 快速访问层
│   - skill_params, _restricted_tools    │
│   - MemoryRef 引用（轻量级）            │
│   - FAQ 标记、临时状态                  │
│   - 小对象（<1KB）、频繁访问            │
│   - 同步 API、无 LRU/TTL                │
└─────────────────┬───────────────────────┘
                  │ 透明代理
                  ↓
┌─────────────────────────────────────────┐
│      Memory (Cold Data Layer)           │  ← 持久化层
│   - Artifact 实际数据                   │
│   - 复杂对象（≥1KB）、长期存储          │
│   - LRU 缓存、TTL 过期                  │
│   - 多存储后端（Memory/File/DB）        │
│   - 异步 API、批量操作                  │
└─────────────────────────────────────────┘
```

### 2.3 设计原则

1. **向后兼容**: 旧代码无需修改，继续使用 `artifact_storage`
2. **渐进迁移**: 新功能使用 `Memory`，旧代码逐步迁移
3. **智能路由**: 根据数据特性自动选择热/冷存储
4. **透明访问**: shared_memory 提供便捷方法访问 Memory

---

## 3. 详细技术设计

### 3.1 Memory 模块新结构

```
assistant/src/assistant/core/memory/
├── __init__.py                 # 公开接口
├── base.py                     # MemoryBackend, MemoryRef, StorageConfig
├── manager.py                  # MemoryManager, 分层路由逻辑
├── backends/                   # 存储后端实现
│   ├── __init__.py
│   ├── memory_backend.py       # LRU 内存后端
│   ├── file_backend.py         # 文件系统后端
│   ├── hybrid_backend.py       # 混合后端
│   └── db_backend.py           # 数据库后端
├── registry.py                 # 后端注册
├── utils.py                    # 数据路由、迁移工具
└── compat.py                   # 向后兼容层
```

### 3.2 核心类设计

#### 3.2.1 MemoryRef（原名 ArtifactRef）

```python
@dataclass
class MemoryRef:
    """Memory 引用对象，存储在 shared_memory 中"""

    # 基础信息
    id: str                              # Memory ID
    type: str                            # 数据类型（dataset, chart, table, config 等）
    category: str = "artifact"           # 分类：artifact, config, temp, system

    # 存储信息
    size: int = 0                        # 数据大小（字节）
    storage_type: StorageType = StorageType.MEMORY
    storage_key: Optional[str] = None    # 存储后端使用的键

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    # 访问统计（用于热度计算）
    access_count: int = 0                # 访问次数
    last_access: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于存储到 shared_memory）"""
        return {
            "id": self.id,
            "type": self.type,
            "category": self.category,
            "size": self.size,
            "storage_type": self.storage_type.value,
            "storage_key": self.storage_key,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "last_access": self.last_access,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRef":
        """从字典创建（支持旧格式兼容）"""
        # 处理旧格式兼容
        storage_type = StorageType(data.get("storage_type", StorageType.MEMORY))
        if "storage" in data and "storage_type" not in data:
            storage_map = {
                "memory": StorageType.MEMORY,
                "compressed": StorageType.MEMORY,
                "file": StorageType.FILE,
            }
            storage_type = storage_map.get(data.get("storage"), StorageType.MEMORY)

        return cls(
            id=data["id"],
            type=data.get("type", "unknown"),
            category=data.get("category", "artifact"),
            size=data.get("size", 0),
            storage_type=storage_type,
            storage_key=data.get("storage_key"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            access_count=data.get("access_count", 0),
            last_access=data.get("last_access", time.time()),
        )
```

#### 3.2.2 MemoryBackend（原名 ArtifactStorage）

```python
class MemoryBackend(ABC):
    """Memory 存储后端抽象基类"""

    def __init__(self, config: StorageConfig, session_id: str):
        self.config = config
        self.session_id = session_id
        self.logger = logging.getLogger(__name__)

    # 核心操作（必须实现）
    @abstractmethod
    async def store(self, ref: MemoryRef, data: Any) -> MemoryRef:
        """存储数据"""
        pass

    @abstractmethod
    async def load(self, ref: MemoryRef) -> Optional[Any]:
        """加载数据"""
        pass

    @abstractmethod
    async def delete(self, ref: MemoryRef) -> bool:
        """删除数据"""
        pass

    @abstractmethod
    async def exists(self, ref: MemoryRef) -> bool:
        """检查是否存在"""
        pass

    # 批量操作（可选，提供默认实现）
    async def store_batch(self, items: List[tuple[MemoryRef, Any]]) -> List[MemoryRef]:
        """批量存储"""
        results = []
        for ref, data in items:
            result = await self.store(ref, data)
            results.append(result)
        return results

    async def load_batch(self, refs: List[MemoryRef]) -> List[Optional[Any]]:
        """批量加载"""
        results = []
        for ref in refs:
            data = await self.load(ref)
            results.append(data)
        return results

    # 清理操作
    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        """清理过期数据"""
        if older_than_seconds is None:
            older_than_seconds = self.config.ttl

        all_refs = await self.list_all()
        now = time.time()
        to_delete = [ref for ref in all_refs if now - ref.created_at > older_than_seconds]
        count = await self.delete_batch(to_delete)
        return count

    async def list_all(self) -> List[MemoryRef]:
        """列出所有引用"""
        raise NotImplementedError(f"{self.__class__.__name__} does not support listing")

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        all_refs = await self.list_all()
        total_size = sum(ref.size for ref in all_refs)
        return {
            "storage_type": self.config.storage_type.value,
            "session_id": self.session_id,
            "total_count": len(all_refs),
            "total_size": total_size,
        }
```

#### 3.2.3 MemoryManager（新增智能路由）

```python
class MemoryManager:
    """统一 Memory 管理器（带智能分层路由）"""

    def __init__(self, config: Optional[MemoryManagerConfig] = None):
        self.config = config or MemoryManagerConfig()
        self.registry = get_registry()
        self._session_storages: Dict[str, MemoryBackend] = {}
        self._hot_cache: Dict[str, Dict] = {}  # Hot data cache
        self._cleanup_task: Optional[asyncio.Task] = None

        # 启动清理任务
        if self.config.enabled:
            self._start_cleanup_task()

    async def store(
        self,
        session_id: str,
        key: str,
        data: Any,
        category: str = "artifact",
        **metadata
    ) -> MemoryRef:
        """
        智能存储：根据数据特性自动选择存储策略

        策略：
        - Hot data: 直接存入 shared_memory（快速访问）
        - Cold data: 存入 MemoryBackend（持久化）
        """
        # 分析数据特性
        size = self._estimate_size(data)
        access_pattern = self._predict_access_pattern(key, metadata)

        # 路由决策
        if self._is_hot_data(size, access_pattern, category):
            # Hot data: 存储到 hot cache
            return self._store_hot(key, data, category, metadata)
        else:
            # Cold data: 使用 MemoryBackend
            return await self._store_cold(session_id, key, data, category, metadata)

    async def load(self, session_id: str, key: str) -> Any:
        """智能加载：支持 hot/cold 数据透明访问"""
        # 先检查 hot cache
        if key in self._hot_cache:
            return self._hot_cache[key]["value"]

        # 检查是否是 Memory 引用
        storage = self._session_storages.get(session_id)
        if storage:
            ref = MemoryRef(id=key, type="unknown", storage_type=storage.config.storage_type)
            data = await storage.load(ref)
            if data is not None:
                return data

        return None

    def _is_hot_data(self, size: int, pattern: str, category: str) -> bool:
        """
        判断是否应该作为 hot data 存储

        规则：
        1. config/system 类型的数据是 hot
        2. 小对象（< 1KB）是 hot
        3. 高频访问模式是 hot
        4. 默认是 cold
        """
        # Config 类型的数据通常是 hot
        if category in ["config", "system", "temp"]:
            return True

        # 小对象（< 1KB）
        if size < 1024:
            return True

        # 高频访问模式
        if pattern == "frequent":
            return True

        # 默认：cold
        return False

    def _store_hot(self, key: str, data: Any, category: str, metadata: Dict) -> MemoryRef:
        """存储热数据（同步，无需 async）"""
        size = self._estimate_size(data)

        ref = MemoryRef(
            id=key,
            type="hot",
            category=category,
            size=size,
            storage_type=StorageType.MEMORY,
            metadata=metadata,
        )

        self._hot_cache[key] = {
            "value": data,
            "ref": ref,
        }

        return ref

    async def _store_cold(
        self,
        session_id: str,
        key: str,
        data: Any,
        category: str,
        metadata: Dict
    ) -> MemoryRef:
        """存储冷数据（使用 MemoryBackend）"""
        storage = await self._get_storage(session_id)

        # 创建引用
        ref = MemoryRef(
            id=key,
            type="cold",
            category=category,
            size=self._estimate_size(data),
            storage_type=storage.config.storage_type,
            metadata=metadata,
        )

        # 存储数据
        await storage.store(ref, data)

        return ref

    def _estimate_size(self, data: Any) -> int:
        """估算数据大小"""
        import json
        try:
            json_data = json.dumps(data, ensure_ascii=False)
            return len(json_data.encode('utf-8'))
        except Exception:
            return len(str(data))

    def _predict_access_pattern(self, key: str, metadata: Dict) -> str:
        """
        预测访问模式

        规则：
        - 以 _ 开头的 key: system
        - skill_params, _restricted_tools: config
        - art_*: artifact
        """
        if key.startswith("_"):
            return "frequent"
        if key in ["skill_params", "_restricted_tools"]:
            return "frequent"
        return "normal"
```

### 3.3 AgentState 扩展

```python
class AgentState(BaseModel):
    """Agent 状态模型（扩展 Memory 支持）"""

    # ... 现有字段 ...

    shared_memory: Dict[str, Any] = Field(default_factory=dict)

    # 新增便捷方法
    def memory_get(self, key: str, default: Any = None) -> Any:
        """
        从 shared_memory 或 Memory 获取数据（同步接口）

        优先级：
        1. shared_memory 中的直接值
        2. shared_memory 中的 MemoryRef（需要异步加载）
        3. 返回默认值
        """
        # 优先从 shared_memory
        if key in self.shared_memory:
            value = self.shared_memory[key]

            # 检查是否是 MemoryRef
            if isinstance(value, dict) and "id" in value:
                # 返回 MemoryRef 对象，调用方需要异步加载
                return MemoryRef.from_dict(value)

            return value

        return default

    def memory_set(self, key: str, value: Any, category: str = "temp") -> None:
        """
        存储数据到 shared_memory（同步接口，热数据）

        适用场景：
        - 小对象（< 1KB）
        - 配置数据（config, system）
        - 临时状态（temp）
        """
        self.shared_memory[key] = {
            "value": value,
            "category": category,
            "updated_at": time.time(),
        }

    def has_memory_ref(self, key: str) -> bool:
        """检查是否有 MemoryRef"""
        if key not in self.shared_memory:
            return False

        value = self.shared_memory[key]
        return isinstance(value, dict) and "id" in value
```

### 3.4 向后兼容层

```python
# memory/compat.py
"""
向后兼容层：支持旧代码继续使用 artifact_storage 接口
"""

# 别名，保持向后兼容
from .base import MemoryBackend as ArtifactStorage
from .base import MemoryRef as ArtifactRef
from .manager import MemoryManager as ArtifactManager

# 旧导入路径的兼容
class _CompatModule:
    """兼容旧导入路径的模块模拟器"""

    def __getattr__(self, name):
        # 将 artifact_storage.xxx 映射到 memory.xxx
        from assistant.core.memory import __all__ as exports

        if name in exports:
            from assistant.core.memory import __dict__ as mem_dict
            return mem_dict.get(name)

        raise AttributeError(f"module {__name__} has no attribute {name}")

# sys.modules 兼容注册
import sys
sys.modules["assistant.core.artifact_storage"] = _CompatModule()
```

---

## 4. 实施步骤

### 阶段 1: 重命名和重构（1-2周）

**任务清单**:
- [ ] 创建新目录 `assistant/src/assistant/core/memory/`
- [ ] 重命名核心类
  - `ArtifactStorage` → `MemoryBackend`
  - `ArtifactRef` → `MemoryRef`
  - `ArtifactManager` → `MemoryManager`
- [ ] 移动并更新所有子模块
  - `memory.py` → `backends/memory_backend.py`
  - `file.py` → `backends/file_backend.py`
  - `hybrid.py` → `backends/hybrid_backend.py`
  - `database.py` → `backends/db_backend.py`
- [ ] 更新 `base.py` 中的类定义
- [ ] 更新 `manager.py` 中的管理逻辑
- [ ] 添加 `compat.py` 兼容层
- [ ] 更新所有 `__init__.py` 导出

**预期成果**:
- 新的 `Memory` 模块结构完整
- `artifact_storage` 目录保持不变（向后兼容）
- 两者可以共存

### 阶段 2: 扩展 MemoryManager（1-2周）

**任务清单**:
- [ ] 实现智能路由逻辑
  - `_is_hot_data()` - 热数据判断
  - `_store_hot()` - 热数据存储
  - `_store_cold()` - 冷数据存储
- [ ] 添加热数据缓存（_hot_cache）
- [ ] 实现 `MemoryRef` 的访问统计字段
- [ ] 更新单元测试

**预期成果**:
- MemoryManager 支持分层路由
- 自动选择热/冷存储策略

### 阶段 3: 扩展 AgentState（1周）

**任务清单**:
- [ ] 添加便捷方法
  - `memory_get()`
  - `memory_set()`
  - `has_memory_ref()`
- [ ] 更新序列化/反序列化逻辑（确保兼容）
- [ ] 添加单元测试

**预期成果**:
- AgentState 提供便捷的 Memory 访问接口
- 向后兼容 shared_memory 的使用方式

### 阶段 4: 迁移新功能（持续进行）

**任务清单**:
- [ ] 新功能代码使用 `Memory` 模块
- [ ] 文档更新
- [ ] 示例代码更新
- [ ] 逐步迁移旧代码（可选）

**预期成果**:
- 新功能使用统一的 Memory 接口
- 旧代码继续通过兼容层工作

### 阶段 5: 清理和优化（未来）

**任务清单**:
- [ ] 评估是否需要完全迁移旧代码
- [ ] 性能测试和优化
- [ ] 文档完善
- [ ] 删除 `artifact_storage` 目录（如果完全迁移）

**预期成果**:
- 代码库统一使用 Memory 模块
- 性能优化完成

---

## 5. 迁移策略

### 5.1 数据路由规则

**Hot Data Criteria**:
- 大小 < 1KB
- 访问频率 > 10 次/分钟
- 生命周期 < 1 小时
- 类型: config, system, temp
- 示例: skill_params, _restricted_tools, FAQ 标记

**Cold Data Criteria**:
- 大小 ≥ 1KB
- 访问频率 ≤ 10 次/分钟
- 生命周期 ≥ 1 小时
- 类型: artifact, dataset, chart, table
- 示例: 大型数据集、图表、表格数据

### 5.2 自动迁移机制

```python
async def migrate_legacy_data(state: AgentState, memory_mgr: MemoryManager) -> int:
    """
    迁移旧格式数据到新的 Memory 系统

    迁移规则：
    1. 检测旧格式（直接存储数据，无 MemoryRef）
    2. 根据数据特性选择存储策略
    3. 更新 shared_memory 引用
    """
    migrated_count = 0

    for key, value in list(state.shared_memory.items()):
        # 检测旧格式（直接存储数据）
        if isinstance(value, (dict, list)) and not isinstance(value, dict) or "id" not in str(value):
            # 估算大小
            size = memory_mgr._estimate_size(value)

            # 迁移决策
            if size >= 1024 or key.startswith('art_'):
                # 迁移到 Memory（冷数据）
                ref = await memory_mgr.store(
                    session_id=state.session_id,
                    key=key,
                    data=value,
                    category="legacy",
                )
                state.shared_memory[key] = ref.to_dict()
                migrated_count += 1
            else:
                # 保持为热数据，但添加元数据
                state.shared_memory[key] = {
                    "value": value,
                    "category": "temp",
                    "migrated": True,
                }
                migrated_count += 1

    return migrated_count
```

### 5.3 兼容性保证

1. **导入兼容**:
```python
# 旧代码（继续工作）
from assistant.core.artifact_storage import ArtifactStorage, ArtifactRef

# 新代码
from assistant.core.memory import MemoryBackend, MemoryRef
```

2. **API 兼容**:
```python
# 旧代码
artifact_mgr = ArtifactManager()
ref = await artifact_mgr.store(session_id, artifact_id, data)

# 新代码（API 相同）
memory_mgr = MemoryManager()
ref = await memory_mgr.store(session_id, key, data)
```

3. **数据兼容**:
```python
# 旧格式
shared_memory["art_123"] = {"id": "art_123", "storage": "memory", ...}

# 新格式（自动兼容）
shared_memory["art_123"] = MemoryRef(...).to_dict()
```

---

## 6. 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 重命名破坏导入 | 高 | 中 | 创建兼容层别名 |
| 异步 API 不兼容 | 中 | 高 | 提供同步包装器 |
| 性能下降 | 中 | 低 | Hot data 走快速路径 |
| 数据丢失风险 | 高 | 低 | 充分测试迁移逻辑 |
| 迁移时间过长 | 低 | 中 | 渐进式迁移，不影响新功能 |

### 回滚计划

如果迁移出现问题，可以：
1. 保留 `artifact_storage` 目录不变
2. 新代码切换回旧导入路径
3. 数据库中保存旧格式数据，无需转换

---

## 7. 测试策略

### 7.1 单元测试

- [ ] MemoryRef 序列化/反序列化
- [ ] MemoryManager 智能路由逻辑
- [ ] 各存储后端（MemoryBackend 子类）
- [ ] AgentState 便捷方法
- [ ] 兼容层功能

### 7.2 集成测试

- [ ] Agent 运行时使用 Memory
- [ ] Artifact 存储和加载
- [ ] 并发访问性能
- [ ] 迁移数据验证

### 7.3 性能测试

- [ ] Hot data 访问延迟（目标 < 1ms）
- [ ] Cold data 访问延迟（目标 < 10ms）
- [ ] LRU 缓存命中率
- [ ] 内存占用对比

---

## 8. 文档更新

### 8.1 需要更新的文档

- [ ] API 参考文档
- [ ] 架构设计文档
- [ ] 开发者指南
- [ ] 迁移指南
- [ ] 示例代码

### 8.2 迁移指南

```markdown
# Memory 模块迁移指南

## 迁移检查清单

- [ ] 更新导入路径
- [ ] 更新类名（ArtifactRef → MemoryRef）
- [ ] 更新函数调用（如果 API 有变化）
- [ ] 测试功能正常
- [ ] 清理旧代码（可选）

## 示例

### 旧代码
```python
from assistant.core.artifact_storage import ArtifactManager, ArtifactRef

mgr = ArtifactManager()
ref = await mgr.store(session_id, artifact_id, data)
```

### 新代码
```python
from assistant.core.memory import MemoryManager, MemoryRef

mgr = MemoryManager()
ref = await mgr.store(session_id, key, data, category="artifact")
```

## 兼容层

如果不想立即迁移，可以继续使用旧导入路径（兼容层会自动映射）。
```

---

## 9. 未来优化方向

### 9.1 可能的增强

1. **智能预加载**: 根据访问模式预测需要的数据
2. **压缩存储**: 对冷数据进行压缩
3. **分布式存储**: 支持远程存储后端（Redis, S3）
4. **访问审计**: 记录数据访问日志
5. **TTL 分级**: 不同类型数据使用不同 TTL

### 9.2 性能优化

1. **批量操作优化**: 减少网络/IO 次数
2. **缓存预取**: 根据访问模式预加载
3. **异步队列**: 批量写入操作
4. **内存池**: 减少对象创建开销

---

## 10. 附录

### 10.1 术语表

| 术语 | 定义 |
|------|------|
| Hot Data | 频繁访问、小对象、短期数据 |
| Cold Data | 低频访问、大对象、长期数据 |
| MemoryRef | Memory 引用对象（轻量级） |
| MemoryBackend | 存储后端抽象 |
| MemoryManager | 统一 Memory 管理器 |

### 10.2 相关文档

- [CLAUDE.md](../CLAUDE.md) - 项目开发指南
- [artifact_storage/base.py](../src/assistant/core/artifact_storage/base.py) - 当前实现
- [agent.py](../src/assistant/core/agent.py) - Agent 实现

---

## 更新历史

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2025-01-17 | 0.1 | 初始版本，规划完成 |

---

**作者**: Claude Code
**审核状态**: 待审核
**下一步**: 等待审核后开始实施
