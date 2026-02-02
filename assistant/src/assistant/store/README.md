# System Store 模块

该模块提供“系统级存储基础设施”，用于承接多个子系统的底层存储需求。
上层子系统保持各自的 **domain API**，仅在底层对接 Store。

建议的对接关系（折中路线）：

- `EventStore` -> uses Store
- `ArtifactStore` -> uses Store
- `SessionMemory` -> uses Store

这样可以统一存储能力（可插拔、可观测、可回放），又避免业务逻辑混在一起。

## 1) Store 类型与内置实现

- `memory`：纯内存
- `file`：本地文件
- `hybrid`：内存 + 文件
- `database`：本地 SQLite
- `remote`：远程（API/WAL）

内置实现位于：`assistant/store/stores/`

- `MemoryOnlyStore`
- `FileMemoryStore`
- `HybridMemoryStore`
- `SQLiteMemoryStore`
- `RemoteMemoryStore`

## 2) 注册与插件加载

注册机制：`store/registry.py`

```python
from assistant.store import register_store, StoreType

@register_store(StoreType.FILE)
class MyFileStore(...):
    ...
```

支持 entrypoint 自动发现：

```
[project.entry-points."assistant.system_stores"]
memory = "your_pkg.memory_store:MyMemoryStore"
```

## 3) StoreManager

`StoreManager` 提供统一入口：

```python
from assistant.store import StoreManager

mgr = StoreManager()
await mgr.store(scope_id="session_1", item_id="k1", item_type="text", data={"a": 1})
```

## 4) 外部注入

支持注入自定义 store 或工厂：

```python
mgr.inject_store("session_1", my_store)
mgr.inject_store_factory(lambda sid: MyStore(sid, my_cfg))
```
