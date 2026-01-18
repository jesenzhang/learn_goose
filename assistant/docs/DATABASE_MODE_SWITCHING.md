# 数据库模式切换指南

## 概述

Assistant 支持两种数据库模式：
- **远程模式**：通过 HTTP API 操作远程数据库
- **本地模式**：使用本地 SQLite 数据库

本指南详细说明如何在两种模式之间切换，以及相关的配置和故障排查方法。

---

## 快速开始

### 本地开发（推荐）

```bash
# 设置环境变量切换到本地模式
export USE_REMOTE_DB=false

# 启动应用
python -m assistant.main
```

### 远程数据库（生产）

```bash
# 设置环境变量切换到远程模式
export USE_REMOTE_DB=true
export REMOTE_DB_URL="http://192.168.11.11:9980/api"
export REMOTE_DB_API_KEY="your-api-key"

# 启动应用
python -m assistant.main
```

---

## 配置方式

### 方式 1: 环境变量（推荐）

环境变量优先级最高，无需修改配置文件即可切换模式：

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| `USE_REMOTE_DB` | 是否使用远程数据库 | false | true/false |
| `REMOTE_DB_URL` | 远程数据库 URL | null | http://192.168.11.11:9980/api |
| `REMOTE_DB_API_KEY` | 远程数据库 API Key | null | your-api-key |
| `LOCAL_DB_PATH` | 本地数据库路径 | museum_assistant.db | ./agent_dev.db |
| `ENVIRONMENT` | 运行环境 | dev | dev/prod/staging |

**示例**：
```bash
# 本地开发
export USE_REMOTE_DB=false
export LOCAL_DB_PATH="./dev.db"
export ENVIRONMENT=dev

# 生产部署
export USE_REMOTE_DB=true
export REMOTE_DB_URL="https://prod-db.example.com/api"
export REMOTE_DB_API_KEY="${DB_API_KEY}"
export ENVIRONMENT=prod
```

### 方式 2: 配置文件

编辑 `assistant_config.yaml`:

```yaml
database:
  # 模式选择
  use_remote: false  # 或 true

  # 远程数据库配置
  remote_db_url: "http://192.168.11.11:9980/api"
  remote_db_api_key: null
  remote_db_timeout: 30

  # 本地数据库配置
  local_db_path: "museum_assistant.db"

  # 健康检查配置
  health_check_enabled: true
  health_check_timeout: 5
```

**注意**：如果同时设置了环境变量和配置文件，环境变量优先级更高。

---

## 切换场景

### 场景 1: 本地开发

**目标**：在本地开发环境使用 SQLite 数据库，便于快速迭代和调试。

**步骤**：
```bash
# 1. 切换到本地模式
export USE_REMOTE_DB=false
export LOCAL_DB_PATH="./agent_dev.db"

# 2. 设置开发环境（启用详细日志）
export ENVIRONMENT=dev

# 3. 启动应用
python -m assistant.main
```

**特点**：
- ✅ 数据保存在本地文件
- ✅ 无需网络连接
- ✅ 调试日志详细
- ✅ 快速重启

### 场景 2: 远程测试

**目标**：测试远程数据库集成，验证 API 兼容性。

**步骤**：
```bash
# 1. 切换到远程模式
export USE_REMOTE_DB=true
export REMOTE_DB_URL="http://192.168.11.11:9980/api"

# 2. （可选）设置 API Key
export REMOTE_DB_API_KEY="test-api-key"

# 3. 启动应用
python -m assistant.main
```

**特点**：
- ✅ 数据存储在远程数据库
- ✅ 多实例共享数据
- ✅ 详细的远程 API 日志

### 场景 3: 生产部署

**目标**：在生产环境使用远程数据库，启用安全配置。

**步骤**：
```bash
# 1. 设置生产环境
export ENVIRONMENT=prod

# 2. 配置远程数据库（使用 HTTPS）
export USE_REMOTE_DB=true
export REMOTE_DB_URL="https://prod-db.example.com/api"
export REMOTE_DB_API_KEY="${DB_API_KEY}"

# 3. 启动应用
python -m assistant.main
```

**特点**：
- ✅ 生产级日志（简洁）
- ✅ HTTPS 安全连接
- ✅ API Key 认证
- ✅ 健康检查自动验证

---

## 错误处理

### 远程数据库错误

#### 错误 1: 连接超时

**错误消息**：
```
[REMOTE DB] Connection timeout
Hint: 远程数据库连接超时或失败，建议切换到本地模式：USE_REMOTE_DB=false
```

**解决方法**：
1. 检查远程数据库 URL 是否正确
2. 测试网络连接：`curl http://192.168.11.11:9980/health`
3. 检查防火墙设置
4. 临时切换到本地模式：`export USE_REMOTE_DB=false`

#### 错误 2: 认证失败 (401)

**错误消息**：
```
[REMOTE DB] 401 Unauthorized
Hint: 远程数据库认证失败，请检查 API Key 或 Token
```

**解决方法**：
1. 检查 `REMOTE_DB_API_KEY` 环境变量
2. 检查配置文件中的 `remote_db_api_key`
3. 确认 API Key 是否有效且未过期
4. 检查是否有权限访问该数据库

#### 错误 3: 资源不存在 (404)

**错误消息**：
```
[REMOTE DB] 404 Not Found
Hint: 远程数据库资源不存在，请检查会话 ID 或 API 端点
```

**解决方法**：
1. 检查会话 ID 是否正确
2. 检查 API 端点是否正确
3. 确认远程数据库服务器配置正确

#### 错误 4: 服务器错误 (500/502/503)

**错误消息**：
```
[REMOTE DB] 503 Service Unavailable
Hint: 远程数据库服务器错误，请稍后重试或联系管理员
```

**解决方法**：
1. 检查远程数据库服务器状态
2. 查看服务器日志
3. 联系数据库管理员
4. 临时切换到本地模式继续工作

### 本地数据库错误

#### 错误 1: 数据库锁定

**错误消息**：
```
[LOCAL DB] database is locked
Hint: 本地数据库被锁定，请检查是否有其他进程正在使用
```

**解决方法**：
1. 检查是否有其他 Python 进程正在运行
2. 关闭所有应用实例
3. 删除数据库锁文件：`rm agent_dev.db-wal` 和 `rm agent_dev.db-shm`
4. 重启应用

#### 错误 2: 表不存在

**错误消息**：
```
[LOCAL DB] no such table: sessions
Hint: 本地数据库表不存在，请检查数据库文件
```

**解决方法**：
1. 删除现有数据库文件：`rm agent_dev.db`
2. 重启应用（会自动创建新数据库）
3. 检查数据库文件路径配置

#### 错误 3: 权限错误

**错误消息**：
```
[LOCAL DB] unable to open database file: Permission denied
Hint: 本地数据库文件权限错误，请检查文件访问权限
```

**解决方法**：
1. 检查数据库文件权限：`ls -l agent_dev.db`
2. 修改权限：`chmod 644 agent_dev.db`
3. 确保当前用户有读写权限
4. 检查目录权限

---

## 健康检查

应用启动时会自动执行数据库健康检查：

### 启用健康检查（默认）

```yaml
database:
  health_check_enabled: true
  health_check_timeout: 5
```

**效果**：
- ✅ 启动时验证数据库连接
- ✅ 健康检查失败阻止应用启动
- ✅ 提供清晰的错误信息

### 禁用健康检查

```yaml
database:
  health_check_enabled: false
```

**效果**：
- ⚠️ 启动时不验证数据库连接
- ⚠️ 可能导致运行时才发现错误
- ⚠️ 仅建议在特殊情况下禁用

---

## 日志级别

根据环境和数据库模式自动调整日志级别：

| 环境 | 数据库模式 | 日志级别 | 说明 |
|------|-----------|---------|------|
| dev  | remote    | DEBUG   | 详细日志，包含 API 请求详情 |
| dev  | local     | INFO    | 正常日志，包含关键操作 |
| prod | remote    | INFO    | 简洁日志，仅记录重要事件 |
| prod | local     | INFO    | 简洁日志，仅记录重要事件 |

**手动设置日志级别**（如果需要）：
```python
import logging
logging.getLogger("assistant.db").setLevel(logging.DEBUG)
```

---

## 故障排查

### 问题 1: 启动时健康检查失败

**错误信息**：
```
RuntimeError: Database health check failed.
Mode: remote
Remote URL: http://192.168.11.11:9980/api
Suggestion: Set USE_REMOTE_DB=false to use local database
```

**排查步骤**：
1. 检查远程数据库 URL 是否正确
2. 测试远程数据库是否可访问：
   ```bash
   curl http://192.168.11.11:9980/health
   ```
3. 检查网络连接和防火墙设置
4. 切换到本地模式验证应用本身是否正常：
   ```bash
   export USE_REMOTE_DB=false
   python -m assistant.main
   ```

### 问题 2: 远程数据库认证失败

**错误信息**：
```
[REMOTE DB] 401 Unauthorized
Hint: 远程数据库认证失败，请检查 API Key 或 Token
```

**排查步骤**：
1. 检查环境变量：`echo $REMOTE_DB_API_KEY`
2. 检查配置文件中的 `remote_db_api_key`
3. 确认 API Key 格式是否正确
4. 测试 API Key：
   ```bash
   curl -H "Authorization: your-api-key" http://192.168.11.11:9980/api/health
   ```

### 问题 3: 本地数据库文件不存在

**错误信息**：
```
[LOCAL DB] no such table: sessions
Hint: 本地数据库表不存在，请检查数据库文件
```

**排查步骤**：
1. 删除现有数据库文件：`rm agent_dev.db`
2. 检查 `local_db_path` 配置是否正确
3. 确保有文件系统写入权限
4. 重启应用（会自动创建新数据库）

### 问题 4: 数据库操作失败但没有详细错误信息

**排查步骤**：
1. 确保在开发环境：`export ENVIRONMENT=dev`
2. 查看应用日志文件：`tail -f museum_assistant.log`
3. 检查数据库日志（如果有）
4. 启用 DEBUG 日志级别：
   ```bash
   export ENVIRONMENT=dev
   export LOG_LEVEL=DEBUG
   ```

---

## 最佳实践

### 开发环境
1. 使用本地 SQLite 数据库
2. 启用详细日志（ENVIRONMENT=dev）
3. 定期清理测试数据
4. 使用内存数据库加快测试（`:memory:`）

### 测试环境
1. 使用远程数据库测试集成
2. 模拟各种错误场景
3. 验证健康检查功能
4. 测试模式切换

### 生产环境
1. 使用远程数据库
2. 设置生产环境（ENVIRONMENT=prod）
3. 使用 HTTPS 连接
4. 配置合理的超时时间
5. 监控数据库性能

---

## 高级配置

### 环境变量优先级

优先级从高到低：
1. 环境变量
2. 配置文件
3. 默认值

**示例**：
```bash
# 环境变量会覆盖配置文件
export USE_REMOTE_DB=false  # 即使配置文件中 use_remote: true，也会使用本地模式
```

### 配置验证

应用启动时会验证数据库配置：

```python
from assistant.db.factory import validate_database_config

errors = validate_database_config({
    "use_remote": True,
    "remote_db_url": None  # 错误：缺少远程数据库 URL
})

# errors: ["remote_db_url is required when use_remote=true"]
```

### 自定义日志格式

```python
import logging

# 配置日志格式
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('custom.log', encoding='utf-8')
    ]
)
```

---

## 附录

### 环境变量完整列表

| 环境变量 | 类型 | 默认值 | 说明 |
|---------|------|--------|------|
| `USE_REMOTE_DB` | bool | false | 是否使用远程数据库 |
| `REMOTE_DB_URL` | string | null | 远程数据库 URL |
| `REMOTE_DB_API_KEY` | string | null | 远程数据库 API Key |
| `LOCAL_DB_PATH` | string | museum_assistant.db | 本地数据库路径 |
| `ENVIRONMENT` | string | dev | 运行环境（dev/prod/staging） |
| `LOG_LEVEL` | string | INFO | 日志级别（DEBUG/INFO/WARNING/ERROR） |

### 配置文件示例

**本地数据库配置**：
```yaml
database:
  use_remote: false
  local_db_path: "./agent_dev.db"
  health_check_enabled: true
  health_check_timeout: 5
```

**远程数据库配置**：
```yaml
database:
  use_remote: true
  remote_db_url: "http://192.168.11.11:9980/api"
  remote_db_api_key: null
  remote_db_timeout: 30
  health_check_enabled: true
  health_check_timeout: 10
```

---

## 相关文档

- [数据库模块实现](../src/assistant/db/README.md)
- [配置指南](../docs/CONFIGURATION.md)
- [故障排查手册](../docs/TROUBLESHOOTING.md)
- [API 参考文档](../docs/API_REFERENCE.md)

---

**文档版本**: 1.0
**最后更新**: 2025-01-17
