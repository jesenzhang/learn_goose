# 文博助手项目总结

## 项目概述

文博助手是一个基于 Skill MicroAgent 的博物馆智能问答服务，实现了会话恢复、事件驱动、事件回放、断线重连和远端数据库支持等高级功能。

## 已实现的功能

### 1. 核心功能

#### 会话恢复
- **实现位置**: `src/assistant/db/__init__.py`, `src/assistant/models/session_manager.py`
- **功能说明**:
  - 自动保存会话状态到数据库
  - 支持会话加载和恢复
  - 会话状态包括对话历史、共享内存、活动技能等

#### 事件驱动
- **实现位置**: `src/assistant/core/events.py`, `src/assistant/api/routes.py`
- **功能说明**:
  - 实时推送处理事件到客户端
  - 支持 Server-Sent Events (SSE) 流式传输
  - 事件类型包括：TOKEN（文本流）、TOOL_START（工具开始）、TOOL_END（工具结束）、ERROR（错误）等

#### 事件回放
- **实现位置**: `src/assistant/models/event_replay.py`
- **功能说明**:
  - 支持历史事件回放
  - 支持事件导出/导入（JSON 格式）
  - 提供事件统计功能
  - 支持按时间范围过滤事件

#### 断线重连
- **实现位置**: `src/assistant/models/session_manager.py`
- **功能说明**:
  - 自动检测断线状态
  - 支持会话状态同步
  - 可配置重连超时时间
  - 保留会话上下文和记忆

#### 远端数据库
- **实现位置**: `src/assistant/db/remote_db.py`, `src/assistant/db/__init__.py`
- **功能说明**:
  - 通过 HTTP API 操作远端数据库
  - 统一的数据库接口，自动切换本地/远端模式
  - 支持健康检查
  - 异步操作，支持连接池

### 2. 文博功能

#### 博物馆知识技能
- **实现位置**: `agent_skills/museum_knowledge/`
- **功能说明**:
  - 文物搜索和详细信息查询
  - 展览信息获取（常展/特展）
  - 历史时期讲解
  - 多文物对比分析

#### 工具函数
- `search_artifact` - 搜索文物
- `get_artifact_detail` - 获取文物详细信息
- `get_exhibition_info` - 获取展览信息
- `explain_era` - 讲解历史时期
- `compare_artifacts` - 对比多个文物

## 项目结构

```
assistant/
├── src/assistant/                    # 源代码目录
│   ├── api/                         # API 路由层
│   │   ├── __init__.py
│   │   └── routes.py               # FastAPI 路由定义
│   ├── config/                      # 配置管理
│   │   ├── __init__.py
│   │   ├── loader.py               # 配置加载器
│   │   └── models.py               # 配置模型
│   ├── core/                        # 核心代理逻辑
│   │   ├── __init__.py
│   │   ├── agent.py                # MicroAgent 主类
│   │   ├── events.py               # 事件管理
│   │   ├── executor.py             # 工具执行器
│   │   ├── generation.py           # 代理代管理
│   │   ├── state.py                # AgentState 模型
│   │   └── watcher.py              # 配置监听
│   ├── db/                          # 数据库管理
│   │   ├── __init__.py             # 统一数据库接口
│   │   ├── manager.py              # 本地 SQLite 管理器
│   │   └── remote_db.py            # 远端数据库管理器
│   ├── models/                      # 数据模型
│   │   ├── event_replay.py          # 事件回放管理器
│   │   └── session_manager.py       # 会话管理器
│   ├── providers/                   # LLM 提供商
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseLLM 抽象类
│   │   ├── factory.py              # 提供商工厂
│   │   ├── openai.py               # OpenAI 实现
│   │   ├── embedding.py            # 嵌入服务
│   │   └── rerank.py               # 重排序服务
│   ├── conversation/                # 对话模型
│   │   ├── __init__.py
│   │   ├── conversation.py         # 对话模型
│   │   └── message.py              # 消息模型
│   ├── intent/                      # 意图识别
│   │   ├── __init__.py
│   │   ├── recognizer.py           # 意图识别器
│   │   ├── strategy.py             # 意图执行策略
│   │   ├── config_loader.py         # 意图配置加载
│   │   ├── models.py               # 意图模型
│   │   ├── handler.py              # 意图处理器
│   │   ├── hooks.py                # 钩子函数
│   │   └── museum_handlers.py      # 博物馆专用处理器
│   ├── skills/                      # 技能系统
│   │   ├── __init__.py
│   │   ├── loader.py               # 技能加载器
│   │   ├── base.py                 # 技能基类
│   │   ├── context.py              # 技能上下文
│   │   └── generic.py              # 通用技能
│   ├── utils/                       # 工具函数
│   │   ├── __init__.py
│   │   ├── concurrency.py          # 并发工具
│   │   ├── template.py             # 模板引擎
│   │   ├── token_counter.py        # Token 计数器
│   │   └── json_repair.py          # JSON 修复工具
│   ├── __init__.py                 # 包初始化
│   └── main.py                     # 主程序入口
├── agent_skills/                    # 技能脚本目录
│   └── museum_knowledge/           # 博物馆知识技能
│       ├── SKILL.md                # 技能描述
│       └── scripts/
│           └── tools.py            # 工具函数
├── tests/                           # 测试目录
│   └── (待添加测试文件)
├── assistant_config.yaml           # 主配置文件
├── .env.example                     # 环境变量示例
├── .gitignore                       # Git 忽略文件
├── pyproject.toml                   # Python 项目配置
├── requirements.txt                  # Python 依赖
├── example_client.py                # 示例客户端
└── README.md                        # 项目说明文档
```

## 配置说明

### 环境变量 (`.env`)

```bash
# OpenAI API Key（必需）
OPENAI_API_KEY=your_openai_api_key_here

# 服务配置
ASSISTANT_PORT=8400
ASSISTANT_HOST=0.0.0.0
ASSISTANT_CONFIG=assistant_config.yaml

# 远端数据库（可选）
REMOTE_DB_URL=http://your-db-server:8500
REMOTE_DB_API_KEY=your_api_key_here

# 日志配置
LOG_LEVEL=INFO
```

### 主配置文件 (`assistant_config.yaml`)

- `agent` - 代理名称和系统提示词
- `provider` - LLM 提供商配置（OpenAI、温度、模型等）
- `database` - 数据库配置（本地/远端）
- `skills_config` - 技能配置（全局技能/上下文技能）
- `intents` - 意图配置（意图定义、槽位、执行模式）

## API 接口

### 主要端点

1. **GET /** - 服务信息
2. **GET /health** - 健康检查
3. **POST /chat/{session_id}** - 发送消息（支持流式）
4. **GET /sessions** - 获取会话列表
5. **POST /chat/{session_id}/reconnect** - 会话重连
6. **GET /events/{session_id}** - 事件回放
7. **GET /agent/{session_id}/state** - 获取会话状态
8. **POST /agent/{session_id}/approval** - 批准工具执行

## 使用示例

### 启动服务

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 OPENAI_API_KEY

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python -m assistant.main
# 或
uvicorn assistant.main:app --host 0.0.0.0 --port 8400
```

### 运行示例客户端

```bash
# 在另一个终端
python example_client.py
```

### curl 测试

```bash
# 基本对话
curl -X POST http://localhost:8400/chat/session1 \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍一下唐三彩"}'

# 流式输出
curl -N -X POST http://localhost:8400/chat/session1 \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍一下唐三彩", "stream": true}'

# 会话重连
curl -X POST http://localhost:8400/chat/session1/reconnect

# 事件回放
curl "http://localhost:8400/events/session1?since=2024-01-01T00:00:00"
```

## 技术亮点

1. **统一的数据库接口** - 自动切换本地/远端模式
2. **事件驱动架构** - 实时推送，支持 SSE
3. **会话生命周期管理** - 创建、活跃、空闲、断线、重连
4. **技能热加载** - 无需重启服务即可更新技能
5. **意图识别** - 自动识别用户意图并执行相应动作
6. **并发工具执行** - 支持并行执行多个工具
7. **流式响应** - 实时输出 LLM 生成内容

## 扩展指南

### 添加新技能

1. 在 `agent_skills/` 创建新目录
2. 创建 `SKILL.md` 描述技能
3. 创建 `scripts/tools.py` 实现工具函数
4. 在配置文件中注册技能

### 添加新工具

在 `agent_skills/{skill_name}/scripts/tools.py` 中添加异步函数：

```python
async def my_tool(param: str, _ctx=None) -> str:
    """工具描述"""
    return f"结果: {param}"
```

### 自定义意图

在 `assistant_config.yaml` 的 `intents` 部分添加新意图：

```yaml
- name: "我的意图"
  examples:
    - "示例1"
    - "示例2"
  slots:
    - name: "param"
      type: "string"
      required: true
  execution:
    mode: "direct"
    action: "my_action"
```

## 注意事项

1. **数据库路径** - 默认使用 `museum_assistant.db`，可配置
2. **OpenAI API Key** - 必须配置才能使用 LLM 功能
3. **端口冲突** - 默认端口 8400，如需修改请更新配置
4. **并发限制** - 默认使用 asyncio，注意协程数量
5. **日志文件** - 日志保存在 `museum_assistant.log`

## 待改进

1. 添加单元测试和集成测试
2. 实现更多文博技能（交互导览、策展助手等）
3. 添加用户认证和权限管理
4. 优化数据库查询性能
5. 添加监控和性能指标
6. 实现批量导入文物数据的功能
7. 添加多语言支持

## 许可证

MIT License

## 联系方式

如有问题或建议，欢迎提交 Issue 或 Pull Request。
