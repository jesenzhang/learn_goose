# 数据库模式切换实施计划

> **状态**: 已规划，等待执行
> **创建日期**: 2025-01-17
> **目标**: 实现本地/远程数据库模式切换，解决远程 API 错误导致流程中断的问题

---

## 1. 问题分析

### 1.1 当前问题

1. **远程数据库错误导致流程无法继续**
   - `RemoteDatabaseManager` 在 API 调用失败时抛出 `RuntimeError`
   - 某些调用点没有异常处理（如 `agent.py:309`）
   - 导致整个请求流程中断

2. **需要本地测试环境**
   - 开发时希望使用本地 SQLite 数据库
   - 不依赖远程 API 可用性
   - 便于快速迭代和测试

3. **缺少灵活的切换机制**
   - 配置已存在（`database.use_remote`），但不够灵活
   - 需要重启应用才能切换模式
   - 开发/生产环境配置无法自动区分

### 1.2 现有实现分析

**配置层** (`assistant_config.yaml`):
```yaml
database:
  use_remote: true                  # 是否使用远程数据库
  remote_db_url: "http://192.168.11.11:9980/gzclabeldebugaapi"
  remote_db_api_key: null
  remote_db_timeout: 30
  local_db_path: "agent_ultra.db"
```

**数据库层** (`db/__init__.py`):
- `UnifiedDatabase` 根据 `use_remote` 在初始化时选择数据库
- 无法运行时切换
- 已有协议接口：`DatabaseProtocol`, `MultiUserDatabaseProtocol`

**错误处理** (`db/remote_db.py`):
- `APIError` 异常类
- `_handle_response()` 统一处理错误
- 方法会抛出 `RuntimeError`（如 save_state, load_state）

**调用点** (`core/agent.py`):
- Line 309: `save_state` 调用**无异常处理**
- Line 102: `_flush_state_save` **有异常处理**
- Line 249: `save_event` **有异常处理**

---

## 2. 设计方案

### 2.1 核心设计原则

1. **错误透明化** - 不掩盖错误，但提供清晰的错误信息
2. **配置灵活化** - 支持环境变量覆盖配置文件
3. **环境感知化** - 自动适配开发/生产环境
4. **日志分级化** - 开发环境详细日志，生产环境简洁日志

### 2.2 架构设计

```
┌─────────────────────────────────────────────┐
│          配置层 (Configuration)             │
│  - assistant_config.yaml                  │
│  - Environment Variables (优先级更高)      │
│  - ENVIRONMENT (dev/prod)                │
└─────────────┬─────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────┐
│      数据库工厂 (Database Factory)        │
│  - 加载配置（支持环境变量覆盖）           │
│  - 创建 UnifiedDatabase 实例              │
│  - 执行健康检查                           │
└─────────────┬─────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────┐
│    统一数据库接口 (UnifiedDatabase)       │
│  - 根据配置选择 Remote/Local              │
│  - 统一的错误处理和日志                   │
│  - 健康检查和重试机制                     │
└─────────────┬─────────────────────────────┘
              │
              ↓
       ┌──────┴──────┐
       ↓             ↓
┌──────────┐  ┌───────────┐
│  Remote  │  │   Local   │
│   DB     │  │    DB     │
└──────────┘  └───────────┘
```

### 2.3 数据库模式切换流程

```
启动应用
    ↓
加载配置 (assistant_config.yaml)
    ↓
检查环境变量
    ↓
确定最终配置
    ↓
创建 UnifiedDatabase 实例
    ↓
执行健康检查
    ↓
[失败] → 记录日志，抛出清晰错误
[成功] → 启动应用
```

### 2.4 错误处理策略

**远程数据库错误**:
```python
try:
    await self.db.save_state(session_id, state)
except RuntimeError as e:
    # 开发环境：详细错误 + 堆栈
    if is_dev_environment():
        logger.error(f"Remote DB error: {e}", exc_info=True)
        await self.events.emit(EventType.ERROR, {
            "error": str(e),
            "error_type": "DatabaseError",
            "hint": "切换到本地模式：设置 USE_REMOTE_DB=false"
        })
    # 生产环境：简洁错误
    else:
        logger.error(f"Remote DB error: {e}")
        await self.events.emit(EventType.ERROR, {
            "error": "Database operation failed",
            "error_type": "DatabaseError"
        })
    raise  # 重新抛出，终止流程
```

**本地数据库错误**:
```python
try:
    await self.db.save_state(session_id, state)
except Exception as e:
    logger.error(f"Local DB error: {e}", exc_info=True)
    # 本地数据库错误同样抛出，但更详细（因为是开发环境）
    await self.events.emit(EventType.ERROR, {
        "error": f"Database error: {str(e)}",
        "error_type": "DatabaseError",
        "hint": "检查数据库文件路径和权限"
    })
    raise
```

---

## 3. 实施步骤

### 阶段 1: 配置层增强（1-2天）

#### 1.1 新增配置项

在 `assistant_config.yaml` 中添加：
```yaml
database:
  # 模式选择（use_remote 的别名，更清晰）
  mode: "remote"  # remote, local, auto

  # 环境覆盖支持
  # 环境变量：USE_REMOTE_DB (true/false), REMOTE_DB_URL, LOCAL_DB_PATH

  # 远程数据库配置
  remote_db_url: "http://192.168.11.11:9980/gzclabeldebugaapi"
  remote_db_api_key: null
  remote_db_timeout: 30
  remote_db_retry_count: 3  # 新增：重试次数
  remote_db_retry_delay: 1   # 新增：重试延迟（秒）

  # 本地数据库配置
  local_db_path: "agent_ultra.db"

  # 健康检查配置
  health_check_enabled: true  # 启动时是否执行健康检查
  health_check_timeout: 5      # 健康检查超时（秒）

# 开发环境配置
environment: "dev"  # dev, prod, staging
```

#### 1.2 更新配置模型

在 `config/models.py` 中：
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
import os

class DatabaseConfig(BaseModel):
    """数据库配置模型"""

    # 模式选择
    mode: Optional[str] = None  # 从配置文件读取，最终由 factory 决定
    use_remote: bool = Field(default=False, description="是否使用远程数据库（兼容旧版）")

    # 远程数据库配置
    remote_db_url: Optional[str] = Field(
        default=None,
        description="远程数据库 URL，可被环境变量 REMOTE_DB_URL 覆盖"
    )
    remote_db_api_key: Optional[str] = Field(
        default=None,
        description="远程数据库 API Key，可被环境变量 REMOTE_DB_API_KEY 覆盖"
    )
    remote_db_timeout: int = Field(default=30, description="远程数据库请求超时（秒）")
    remote_db_retry_count: int = Field(default=3, description="远程数据库重试次数")
    remote_db_retry_delay: int = Field(default=1, description="远程数据库重试延迟（秒）")

    # 本地数据库配置
    local_db_path: str = Field(
        default="agent_ultra.db",
        description="本地数据库路径，可被环境变量 LOCAL_DB_PATH 覆盖"
    )

    # 健康检查配置
    health_check_enabled: bool = Field(default=True, description="启动时是否执行健康检查")
    health_check_timeout: int = Field(default=5, description="健康检查超时（秒）")

    def get_effective_config(self) -> dict:
        """
        获取最终生效的配置（考虑环境变量覆盖）

        Returns:
            {
                "use_remote": bool,
                "remote_db_url": str,
                "remote_db_api_key": str | None,
                "remote_db_timeout": int,
                "local_db_path": str
            }
        """
        # 环境变量优先级高于配置文件
        use_remote_env = os.getenv("USE_REMOTE_DB", "").lower()
        remote_url_env = os.getenv("REMOTE_DB_URL")
        remote_key_env = os.getenv("REMOTE_DB_API_KEY")
        local_path_env = os.getenv("LOCAL_DB_PATH")

        # 确定 use_remote
        if use_remote_env in ("true", "1", "yes"):
            use_remote = True
        elif use_remote_env in ("false", "0", "no"):
            use_remote = False
        else:
            # 如果没有环境变量，使用配置文件
            use_remote = self.use_remote

        return {
            "use_remote": use_remote,
            "remote_db_url": remote_url_env or self.remote_db_url,
            "remote_db_api_key": remote_key_env or self.remote_db_api_key,
            "remote_db_timeout": self.remote_db_timeout,
            "local_db_path": local_path_env or self.local_db_path,
        }

class AppConfig(BaseModel):
    """应用配置模型"""

    # ... 现有字段 ...

    environment: Literal["dev", "prod", "staging"] = Field(
        default="dev",
        description="运行环境"
    )
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
```

### 阶段 2: 数据库工厂（1-2天）

#### 2.1 创建数据库工厂模块

新建 `db/factory.py`：
```python
"""
数据库工厂 - 负责创建和配置数据库实例

职责：
- 加载配置（支持环境变量覆盖）
- 创建 UnifiedDatabase 实例
- 执行健康检查
- 提供配置验证
"""

import logging
import os
from typing import Optional

from . import UnifiedDatabase
from .async_manager import AsyncDatabaseManager
from .remote_db import RemoteDatabaseManager

logger = logging.getLogger(__name__)


def is_dev_environment() -> bool:
    """
    判断是否为开发环境

    优先级：
    1. 环境变量 ENVIRONMENT
    2. 配置文件中的 environment 字段
    3. 默认 dev
    """
    env = os.getenv("ENVIRONMENT", "").lower()
    if env in ("prod", "production"):
        return False
    if env in ("dev", "development"):
        return True
    # 默认为开发环境
    return True


def get_log_level(use_remote: bool) -> str:
    """
    根据环境和数据库模式确定日志级别

    Args:
        use_remote: 是否使用远程数据库

    Returns:
        日志级别字符串 (DEBUG, INFO, WARNING, ERROR)
    """
    if not is_dev_environment():
        return "INFO"

    # 开发环境
    if use_remote:
        return "DEBUG"  # 远程数据库，详细日志便于调试
    else:
        return "INFO"  # 本地数据库，正常日志


async def create_database(config) -> UnifiedDatabase:
    """
    创建数据库实例（工厂方法）

    流程：
    1. 获取最终配置（考虑环境变量覆盖）
    2. 根据配置创建数据库实例
    3. 执行健康检查
    4. 设置日志级别

    Args:
        config: DatabaseConfig 对象

    Returns:
        UnifiedDatabase 实例

    Raises:
        RuntimeError: 健康检查失败
    """
    # 1. 获取最终配置
    effective_config = config.get_effective_config()
    use_remote = effective_config["use_remote"]

    logger.info(f"Creating database instance (mode={'remote' if use_remote else 'local'})")

    # 2. 创建数据库实例
    db = UnifiedDatabase(
        local_db_path=effective_config["local_db_path"],
        remote_db_url=effective_config["remote_db_url"],
        remote_db_api_key=effective_config["remote_db_api_key"],
        use_remote=use_remote,
        timeout=effective_config["remote_db_timeout"]
    )

    # 3. 初始化数据库
    await db.initialize()

    # 4. 健康检查
    if config.health_check_enabled:
        healthy = await db.health_check()
        if not healthy:
            error_msg = (
                f"Database health check failed. "
                f"Mode: {'remote' if use_remote else 'local'}"
            )

            if use_remote:
                error_msg += f"\nRemote URL: {effective_config['remote_db_url']}"
                error_msg += "\nSuggestion: Set USE_REMOTE_DB=false to use local database"

            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info("Database health check passed")

    # 5. 设置日志级别
    log_level = get_log_level(use_remote)
    logger.info(f"Log level set to {log_level}")

    return db


def validate_database_config(config: dict) -> list[str]:
    """
    验证数据库配置是否有效

    Args:
        config: 数据库配置字典

    Returns:
        错误消息列表（空列表表示验证通过）
    """
    errors = []

    use_remote = config.get("use_remote", False)

    if use_remote:
        # 远程模式必需配置
        if not config.get("remote_db_url"):
            errors.append("remote_db_url is required when use_remote=true")

        if config.get("remote_db_url", "").startswith("http://"):
            errors.append("remote_db_url should use HTTPS for security")
    else:
        # 本地模式必需配置
        if not config.get("local_db_path"):
            errors.append("local_db_path is required when use_remote=false")

    return errors
```

#### 2.2 更新数据库初始化

在 `db/__init__.py` 中更新 `configure_db` 函数：
```python
from .factory import create_database, validate_database_config, is_dev_environment

def configure_db(
    config: DatabaseConfig
) -> UnifiedDatabase:
    """
    配置全局数据库实例

    Args:
        config: DatabaseConfig 对象（已加载配置文件）

    Returns:
        配置好的数据库实例（需要调用 initialize() 初始化）

    Raises:
        ValueError: 配置验证失败
    """
    global _global_db

    # 1. 验证配置
    effective_config = config.get_effective_config()
    errors = validate_database_config(effective_config)
    if errors:
        error_msg = "Database configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 2. 记录配置信息
    logger.info(f"Configuring database:")
    logger.info(f"  Mode: {'remote' if effective_config['use_remote'] else 'local'}")
    if effective_config['use_remote']:
        logger.info(f"  Remote URL: {effective_config['remote_db_url']}")
        logger.info(f"  Timeout: {effective_config['remote_db_timeout']}s")
    else:
        logger.info(f"  Local Path: {effective_config['local_db_path']}")
    logger.info(f"  Environment: {'dev' if is_dev_environment() else 'prod'}")

    # 3. 创建数据库实例（延迟初始化）
    _global_db = UnifiedDatabase(
        local_db_path=effective_config["local_db_path"],
        remote_db_url=effective_config["remote_db_url"],
        remote_db_api_key=effective_config["remote_db_api_key"],
        use_remote=effective_config["use_remote"],
        timeout=effective_config["remote_db_timeout"]
    )

    logger.info("Database configured successfully (call initialize() to connect)")
    return _global_db
```

### 阶段 3: 错误处理统一化（2-3天）

#### 3.1 创建数据库错误处理器

新建 `db/error_handler.py`：
```python
"""
数据库错误处理器 - 统一处理数据库错误

职责：
- 捕获数据库异常
- 格式化错误消息
- 发送错误事件
- 记录日志（根据环境调整详细程度）
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """数据库错误基类"""

    def __init__(
        self,
        message: str,
        db_mode: str,
        hint: Optional[str] = None,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.db_mode = db_mode
        self.hint = hint
        self.original_exception = original_exception
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """格式化错误消息"""
        parts = [f"[{self.db_mode.upper()} DB] {self.message}"]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        return "\n".join(parts)


def handle_database_error(
    error: Exception,
    db_mode: str,
    event_emitter=None,
    is_dev: bool = True
) -> DatabaseError:
    """
    处理数据库错误

    Args:
        error: 原始异常
        db_mode: 数据库模式 ("remote" 或 "local")
        event_emitter: 事件发射器（可选）
        is_dev: 是否为开发环境

    Returns:
        DatabaseError 对象
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # 1. 记录日志
    if is_dev:
        # 开发环境：详细日志 + 堆栈
        logger.error(
            f"Database error [{error_type}]: {error_msg}",
            exc_info=error
        )
    else:
        # 生产环境：简洁日志
        logger.error(f"Database error [{error_type}]: {error_msg}")

    # 2. 构造提示信息
    hint = None
    if db_mode == "remote":
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            hint = "远程数据库连接超时或失败，建议切换到本地模式：USE_REMOTE_DB=false"
        elif "401" in error_msg or "403" in error_msg:
            hint = "远程数据库认证失败，请检查 API Key 或 Token"
        elif "404" in error_msg:
            hint = "远程数据库资源不存在"
        elif "500" in error_msg or "502" in error_msg or "503" in error_msg:
            hint = "远程数据库服务器错误，请稍后重试或联系管理员"
    else:
        if "lock" in error_msg.lower() or "database is locked" in error_msg.lower():
            hint = "本地数据库被锁定，请检查是否有其他进程正在使用"
        elif "no such table" in error_msg.lower():
            hint = "本地数据库表不存在，请检查数据库文件"
        elif "permission" in error_msg.lower():
            hint = "本地数据库文件权限错误，请检查文件访问权限"

    # 3. 发送错误事件
    if event_emitter:
        from ..core.events import EventType
        event_emitter.emit(EventType.ERROR, {
            "error": error_msg,
            "error_type": f"DatabaseError ({db_mode})",
            "hint": hint,
            "db_mode": db_mode
        })

    # 4. 返回统一错误
    return DatabaseError(
        message=error_msg,
        db_mode=db_mode,
        hint=hint,
        original_exception=error
    )
```

#### 3.2 更新 UnifiedDatabase

在 `db/__init__.py` 中修改 UnifiedDatabase 的方法，使用错误处理器：
```python
from .error_handler import handle_database_error, DatabaseError
from .factory import is_dev_environment

class UnifiedDatabase:
    # ... 现有代码 ...

    async def save_state(self, session_id: int, state: Dict[str, Any]) -> bool:
        """保存会话状态（带统一错误处理）"""
        try:
            if self._remote_db:
                return await self._remote_db.save_state(session_id, state)
            elif self._local_db:
                return await self._local_db.save_state(session_id, state)
            return False
        except Exception as e:
            # 使用错误处理器
            db_mode = "remote" if self._remote_db else "local"
            handled_error = handle_database_error(
                error=e,
                db_mode=db_mode,
                is_dev=is_dev_environment()
            )
            raise handled_error from e

    async def load_state(self, session_id: int) -> Optional[Dict[str, Any]]:
        """加载会话状态（带统一错误处理）"""
        try:
            if self._remote_db:
                return await self._remote_db.load_state(session_id)
            elif self._local_db:
                return await self._local_db.load_state(session_id)
            return None
        except Exception as e:
            db_mode = "remote" if self._remote_db else "local"
            handled_error = handle_database_error(
                error=e,
                db_mode=db_mode,
                is_dev=is_dev_environment()
            )
            raise handled_error from e

    # ... 对其他方法应用同样的错误处理模式 ...
```

### 阶段 4: 应用启动逻辑更新（1天）

#### 4.1 更新 main.py

```python
async def create_app() -> FastAPI:
    """创建 FastAPI 应用"""

    # 1. 加载配置
    config = ConfigLoader(config_path)

    # 2. 配置数据库（使用工厂方法）
    from .db.factory import create_database

    try:
        db = await create_database(config.database)
        configure_db_instance(db)  # 设置全局实例
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        # 提供清晰的错误信息和解决建议
        if "health check failed" in str(e):
            logger.error("\n" + "="*60)
            logger.error("数据库健康检查失败！")
            logger.error("="*60)
            logger.error("解决方法：")
            logger.error("1. 检查远程数据库是否可访问")
            logger.error("2. 或设置环境变量切换到本地模式：")
            logger.error("   export USE_REMOTE_DB=false")
            logger.error("="*60)
        raise

    # 3. 初始化 Agent
    try:
        agent = MicroAgent(
            config=config,
            db=db
        )
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise

    # 4. 设置全局实例
    set_agent(agent)

    # 5. 创建 FastAPI 应用
    app = FastAPI(title="Assistant API")

    # ... 其他初始化代码 ...

    return app
```

### 阶段 5: 文档和测试（2-3天）

#### 5.1 使用文档

创建 `docs/DATABASE_MODE_SWITCHING.md`：
```markdown
# 数据库模式切换指南

## 概述

Assistant 支持两种数据库模式：
- **远程模式**：通过 HTTP API 操作远程数据库
- **本地模式**：使用本地 SQLite 数据库

## 配置方式

### 方式 1: 配置文件

编辑 `assistant_config.yaml`:
```yaml
database:
  use_remote: true  # 或 false
  remote_db_url: "http://your-remote-db-url"
  local_db_path: "agent_ultra.db"
```

### 方式 2: 环境变量（推荐）

环境变量优先级高于配置文件：

```bash
# 使用远程数据库
export USE_REMOTE_DB=true
export REMOTE_DB_URL="http://192.168.11.11:9980/api"
export REMOTE_DB_API_KEY="your-api-key"

# 使用本地数据库
export USE_REMOTE_DB=false
export LOCAL_DB_PATH="./agent_dev.db"
```

### 方式 3: 开发环境配置

```bash
# 设置环境为开发环境（自动启用详细日志）
export ENVIRONMENT=dev
```

## 切换场景

### 场景 1: 本地开发

```bash
# 方法 A: 修改配置文件
# 编辑 assistant_config.yaml，设置 use_remote: false

# 方法 B: 使用环境变量（推荐）
export USE_REMOTE_DB=false
python -m assistant.main
```

### 场景 2: 远程测试

```bash
# 确保远程数据库可访问
curl http://192.168.11.11:9980/health

# 启动应用
export USE_REMOTE_DB=true
export REMOTE_DB_URL="http://192.168.11.11:9980/api"
python -m assistant.main
```

### 场景 3: 生产部署

```bash
# 设置生产环境
export ENVIRONMENT=prod
export USE_REMOTE_DB=true
export REMOTE_DB_URL="https://prod-db.example.com/api"
export REMOTE_DB_API_KEY="${REMOTE_DB_KEY}"

# 启动应用
python -m assistant.main
```

## 错误处理

### 远程数据库错误

错误消息示例：
```
[REMOTE DB] Connection timeout
Hint: 远程数据库连接超时或失败，建议切换到本地模式：USE_REMOTE_DB=false
```

解决方法：
1. 检查远程数据库是否可访问
2. 检查网络连接
3. 切换到本地模式：`export USE_REMOTE_DB=false`

### 本地数据库错误

错误消息示例：
```
[LOCAL DB] database is locked
Hint: 本地数据库被锁定，请检查是否有其他进程正在使用
```

解决方法：
1. 检查是否有其他进程正在使用数据库
2. 重启应用
3. 删除数据库文件重建

## 健康检查

启动时自动执行健康检查：

```bash
# 启用健康检查（默认）
database:
  health_check_enabled: true
  health_check_timeout: 5

# 禁用健康检查
database:
  health_check_enabled: false
```

健康检查失败会阻止应用启动，并提供清晰的错误信息。

## 日志级别

根据环境和数据库模式自动调整：

| 环境 | 数据库模式 | 日志级别 |
|------|-----------|---------|
| dev  | remote    | DEBUG   |
| dev  | local     | INFO    |
| prod | remote    | INFO    |
| prod | local     | INFO    |

## 故障排查

### 问题 1: 启动时健康检查失败

错误信息：
```
RuntimeError: Database health check failed.
Mode: remote
Remote URL: http://192.168.11.11:9980/api
Suggestion: Set USE_REMOTE_DB=false to use local database
```

解决方法：
1. 检查远程数据库 URL 是否正确
2. 测试远程数据库是否可访问
3. 切换到本地模式：`export USE_REMOTE_DB=false`

### 问题 2: 远程数据库认证失败

错误信息：
```
[REMOTE DB] 401 Unauthorized
Hint: 远程数据库认证失败，请检查 API Key 或 Token
```

解决方法：
1. 检查 `REMOTE_DB_API_KEY` 环境变量
2. 检查配置文件中的 `remote_db_api_key`
3. 确认 API Key 是否有效

### 问题 3: 本地数据库文件不存在

错误信息：
```
[LOCAL DB] no such table: sessions
Hint: 本地数据库表不存在，请检查数据库文件
```

解决方法：
1. 删除现有数据库文件：`rm agent_ultra.db`
2. 重启应用（会自动创建新数据库）
3. 检查 `local_db_path` 配置是否正确
```

#### 5.2 单元测试

创建 `tests/test_database_mode_switching.py`：
```python
import pytest
import os
from assistant.db.factory import (
    create_database,
    is_dev_environment,
    validate_database_config,
    get_log_level
)
from assistant.config.models import DatabaseConfig

def test_is_dev_environment():
    """测试开发环境判断"""
    # 默认开发环境
    os.environ.pop("ENVIRONMENT", None)
    assert is_dev_environment() is True

    # 生产环境
    os.environ["ENVIRONMENT"] = "prod"
    assert is_dev_environment() is False

    os.environ.pop("ENVIRONMENT")


def test_get_effective_config_with_env_override():
    """测试环境变量覆盖配置"""
    config = DatabaseConfig(
        use_remote=True,
        remote_db_url="http://default-url",
        local_db_path="default.db"
    )

    # 环境变量覆盖
    os.environ["USE_REMOTE_DB"] = "false"
    os.environ["LOCAL_DB_PATH"] = "custom.db"

    effective = config.get_effective_config()

    assert effective["use_remote"] is False
    assert effective["local_db_path"] == "custom.db"

    os.environ.pop("USE_REMOTE_DB")
    os.environ.pop("LOCAL_DB_PATH")


def test_validate_database_config():
    """测试配置验证"""

    # 远程模式缺少 URL
    errors = validate_database_config({"use_remote": True})
    assert "remote_db_url is required" in errors

    # 配置正确
    errors = validate_database_config({
        "use_remote": True,
        "remote_db_url": "http://example.com"
    })
    assert len(errors) == 0


def test_get_log_level():
    """测试日志级别获取"""

    # 开发环境 + 远程数据库
    os.environ["ENVIRONMENT"] = "dev"
    assert get_log_level(use_remote=True) == "DEBUG"
    assert get_log_level(use_remote=False) == "INFO"

    # 生产环境
    os.environ["ENVIRONMENT"] = "prod"
    assert get_log_level(use_remote=True) == "INFO"

    os.environ.pop("ENVIRONMENT")


@pytest.mark.asyncio
async def test_create_database_with_health_check():
    """测试数据库创建和健康检查"""

    # 本地数据库（总是健康）
    config = DatabaseConfig(use_remote=False, local_db_path=":memory:")

    db = await create_database(config)
    assert db is not None
    assert db.use_remote is False

    await db.close()
```

---

## 4. 实施优先级

### P0 - 核心功能（必须实现）
- [ ] 配置层增强（环境变量支持）
- [ ] 数据库工厂（create_database）
- [ ] 统一错误处理
- [ ] 更新 UnifiedDatabase 方法
- [ ] 更新 main.py 启动逻辑

### P1 - 重要功能（应该实现）
- [ ] 健康检查
- [ ] 配置验证
- [ ] 开发环境检测
- [ ] 日志级别自动调整

### P2 - 优化功能（可以延后）
- [ ] 单元测试
- [ ] 使用文档
- [ ] 故障排查指南
- [ ] 示例代码

---

## 5. 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 环境变量优先级混乱 | 中 | 低 | 明确文档说明优先级规则 |
| 健康检查误报 | 低 | 中 | 设置合理的超时时间 |
| 错误信息不清晰 | 高 | 低 | 测试各种错误场景 |
| 日志过度详细 | 低 | 中 | 生产环境限制日志级别 |
| 配置兼容性破坏 | 中 | 低 | 保留旧配置字段（use_remote） |

---

## 6. 验收标准

### 功能验收
- [ ] 可以通过环境变量切换数据库模式
- [ ] 可以通过配置文件切换数据库模式
- [ ] 启动时执行健康检查
- [ ] 错误信息清晰且包含解决建议
- [ ] 开发环境日志详细，生产环境日志简洁
- [ ] 远程数据库错误时提供切换到本地的建议

### 测试验收
- [ ] 单元测试覆盖核心功能
- [ ] 本地数据库模式测试通过
- [ ] 远程数据库模式测试通过
- [ ] 环境变量覆盖测试通过
- [ ] 错误处理测试通过

### 文档验收
- [ ] 使用文档完整
- [ ] 配置示例清晰
- [ ] 故障排查指南可用
- [ ] 代码注释充分

---

## 7. 相关文档

- [CLAUDE.md](../CLAUDE.md) - 项目开发指南
- [assistant_config.yaml](../assistant_config.yaml) - 配置文件
- [db/__init__.py](../src/assistant/db/__init__.py) - 数据库接口
- [db/remote_db.py](../src/assistant/db/remote_db.py) - 远程数据库实现
- [core/agent.py](../src/assistant/core/agent.py) - Agent 实现

---

## 更新历史

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2025-01-17 | 0.1 | 初始版本，规划完成 |

---

**作者**: Claude Code
**审核状态**: 待审核
**下一步**: 等待审核后开始实施
