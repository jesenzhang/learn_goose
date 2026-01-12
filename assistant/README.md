# 文博助手 (Museum Assistant)

基于 Skill MicroAgent 的博物馆智能助手服务，提供专业的文物咨询、展览导览和历史知识讲解服务。

## 功能特性

### 核心功能

1. **会话恢复** - 支持会话状态持久化，断开后可恢复之前的对话
2. **事件驱动** - 实时推送处理事件，提供流畅的交互体验
3. **事件回放** - 支持历史事件回放和导出，便于分析和调试
4. **断线重连** - 自动检测并处理断线，支持无缝重连
5. **远端数据库** - 支持通过 HTTP API 操作远端数据库

### 文博功能

- 🏛️ **文物查询** - 搜索和获取文物的详细信息
- 📖 **历史讲解** - 各个历史时期的详细介绍
- 🎨 **展览信息** - 常展和特展的实时信息
- 🗺️ **交互导览** - 沉浸式的博物馆导览体验
- 📊 **文物对比** - 多个文物的对比分析

## 项目结构

```
assistant/
├── src/assistant/           # 源代码目录
│   ├── api/                # API 路由
│   ├── config/             # 配置加载
│   ├── core/               # 核心代理逻辑
│   ├── db/                 # 数据库管理
│   ├── providers/          # LLM 提供商
│   ├── conversation/       # 对话模型
│   ├── intent/             # 意图识别
│   ├── skills/             # 技能系统
│   ├── utils/              # 工具函数
│   └── models/             # 数据模型
├── agent_skills/           # 技能脚本
│   └── museum_knowledge/   # 博物馆知识技能
│       ├── SKILL.md
│       └── scripts/
│           └── tools.py
├── assistant_config.yaml  # 配置文件
├── .env                   # 环境变量
├── museum_assistant.db    # 本地数据库
├── museum_assistant.log   # 日志文件
└── README.md              # 本文件
```

## 安装

### 环境要求

- Python 3.9+
- pip

### 安装步骤

1. 克隆或复制项目到本地

2. 创建并激活虚拟环境（推荐）

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

### 环境变量

创建 `.env` 文件：

```bash
# OpenAI API Key（必需）
OPENAI_API_KEY=your_openai_api_key_here

# 服务配置
ASSISTANT_PORT=8400
ASSISTANT_HOST=0.0.0.0

# 远端数据库（可选）
REMOTE_DB_URL=http://your-db-server:8500
REMOTE_DB_API_KEY=your_api_key_here
```

### 配置文件

修改 `assistant_config.yaml` 以自定义配置：

- `agent` - 代理名称和系统提示词
- `provider` - LLM 提供商配置
- `database` - 数据库配置
- `skills_config` - 技能配置
- `intents` - 意图配置

## 运行

### 启动服务

```bash
# 使用 Python
python -m assistant.main

# 或使用 uvicorn
uvicorn assistant.main:app --host 0.0.0.0 --port 8400
```

### API 端点

启动后访问：

- 服务首页：http://localhost:8400
- API 文档：http://localhost:8400/docs
- 健康检查：http://localhost:8400/health

### 主要 API

#### 发送消息

```bash
POST /chat/{session_id}
{
  "message": "介绍一下唐三彩",
  "resume": false
}
```

#### 获取会话列表

```bash
GET /sessions
```

#### 会话重连

```bash
POST /chat/{session_id}/reconnect
```

#### 事件回放

```bash
GET /events/{session_id}?since=2024-01-01T00:00:00
```

## 技能开发

### 创建新技能

1. 在 `agent_skills/` 下创建技能目录

2. 创建 `SKILL.md` 文件

```markdown
# Skill Name

**Skill Type:** global 或 contextual

**Description:** 技能描述

## 功能介绍

...

## 允许使用的工具

- `tool_name` - 工具描述
```

3. 创建 `scripts/` 目录并添加工具函数

```python
async def my_tool(param: str, _ctx=None) -> str:
    """工具描述"""
    return f"结果: {param}"
```

4. 在配置文件中注册技能

## 使用示例

### Python 客户端

```python
import httpx
import asyncio
from typing import AsyncIterator

async def chat_stream(session_id: str, message: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"http://localhost:8400/chat/{session_id}",
            json={"message": message},
            timeout=60
        ) as response:
            async for chunk in response.aiter_text():
                if chunk.startswith("data: "):
                    data = chunk[6:]
                    print(data)

asyncio.run(chat_stream("my_session", "介绍一下唐三彩"))
```

### curl

```bash
# 普通请求
curl -X POST http://localhost:8400/chat/session1 \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍一下唐三彩"}'

# 流式输出
curl -N -X POST http://localhost:8400/chat/session1 \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍一下唐三彩", "stream": true}'
```

## 数据库

### 本地数据库

默认使用 SQLite，存储在 `museum_assistant.db`

### 远端数据库

配置远端数据库 URL 后自动切换到 HTTP API 模式

远端数据库 API 需要实现以下端点：

- `POST /states` - 保存状态
- `GET /states/{session_id}` - 加载状态
- `DELETE /states/{session_id}` - 删除状态
- `GET /sessions` - 列出会话
- `POST /events` - 保存事件
- `GET /events/{session_id}` - 加载事件
- `GET /health` - 健康检查

## 日志

日志保存在 `museum_assistant.log`

查看日志：

```bash
tail -f museum_assistant.log
```

## 故障排除

### 数据库错误

```bash
# 删除数据库重新初始化
rm museum_assistant.db
python -m assistant.main
```

### 技能加载失败

检查 `agent_skills/` 目录结构是否正确，确保 `SKILL.md` 和 `scripts/` 目录存在

### 连接超时

增加 `assistant_config.yaml` 中的超时设置

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
