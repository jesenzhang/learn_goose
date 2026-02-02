# Memory 模块

本模块提供统一的 memory 管理能力，包含：
- 会话记忆（summary / facts / entities / topics）
- ChatRecall（上下文召回）
- Query Rewrite（独立模块）
- Memory Store（存储后端）

## 1) Store 类型与注册机制

Store 类型遵循如下分类：

- `memory`：纯内存存储
- `file`：本地文件存储
- `hybrid`：内存 + 文件
- `database`：本地 SQLite
  - 可通过插件/远程实现替换为远程 store

默认实现：
- `MemoryOnlyStore`
- `FileMemoryStore`
- `HybridMemoryStore`
- `SQLiteMemoryStore`
 - `RemoteMemoryStore`（通过插件路径使用）

注册机制位于：`memory/stores/registry.py`

你可以用装饰器注册自定义 store：

```python
from assistant.memory.stores import register_store, StoreType

@register_store(StoreType.FILE)
class MyFileStore(...):
    ...
```

或者在配置中使用插件路径：

```yaml
memory:
  store:
    store_type: file
    plugin_path: "my_pkg.my_module:MyStore"
```

插件路径支持两种格式：
- `package.module:ClassName`
- `package.module.ClassName`

### EntryPoint 自动发现

支持 entrypoint 自动发现：

```
[project.entry-points."assistant.memory_stores"]
memory = "your_pkg.memory_store:MyMemoryStore"
file = "your_pkg.file_store:MyFileStore"
```

EntryPoint name 可以直接映射 `StoreType`，或类中声明 `STORE_TYPE`。

## 2) Memory 配置

`assistant_config.yaml` 示例：

```yaml
memory:
  enabled: true
  store:
    enabled: true
    store_type: memory
    base_dir: "memories"
    db_path: "memory_store.db"
    plugin_path: null
    plugin_settings: {}
    memory_threshold: 10240
    file_threshold: 102400
    compression: true
    cleanup_interval: 3600
    ttl: 86400
    max_items: 50
    max_size_bytes: 52428800
    plugin_path: null
    plugin_settings: {}
  chatrecall:
    enabled: true
    ...
```

## 3) 外部注入 Store

你可以在运行时注入自定义 store：

```python
from assistant.memory import get_manager

mem = get_manager()
mem.inject_store(session_id, my_store_instance)
```

或注入工厂：

```python
mem.inject_store_factory(lambda sid: MyStore(sid, my_config))
```

### 远程 Store 注入 auth_provider

如果需要动态 token（来自中间件/请求上下文），请通过构造器注入：

```python
from assistant.memory.stores.remote_store import RemoteMemoryStore
from assistant.utils.ctx_vars import get_auth_token

store = RemoteMemoryStore(
    session_id,
    config=my_config,
    auth_provider=get_auth_token,
)
```

## 4) Query Rewrite

独立模块：`assistant/memory/query_rewrite.py`  
ChatRecall 会使用 `QueryRewriter`。

如需单独调用：

```python
from assistant.memory import QueryRewriter
rewriter = QueryRewriter(config)
```

## 5) 远程 Store（API + WAL）

内置 `RemoteMemoryStore`，通过 `plugin_path` 使用：

```yaml
memory:
  store:
    store_type: database
    plugin_path: "assistant.memory.stores.remote_store:RemoteMemoryStore"
    plugin_settings:
      base_url: "http://127.0.0.1:8080"
      api_key: "xxx"
      auth_header: "Authorization"
      auth_prefix: ""
      signature_secret: "secret"
      retry_count: 3
      retry_backoff: 0.5
      wal_enabled: true
      wal_dir: "memories_wal"
      store_path: "/memory/store"
      load_path: "/memory/load"
      delete_path: "/memory/delete"
      list_path: "/memory/list"
      stats_path: "/memory/stats"
```
