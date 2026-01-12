# 文博助手 - 快速启动指南

## 前置要求

- Python 3.9 或更高版本
- OpenAI API Key
- pip 包管理器

## 5 分钟快速启动

### 步骤 1: 克隆项目

项目已位于 `F:\Workspace\learn_goose\assistant\` 目录

### 步骤 2: 配置环境变量

```bash
cd assistant

# 创建 .env 文件
copy .env.example .env

# 编辑 .env 文件，填入你的 OpenAI API Key
# 将 OPENAI_API_KEY=your_openai_api_key_here 替换为实际的 API Key
```

### 步骤 3: 安装依赖

```bash
# 使用 conda base 环境（推荐）
conda activate base

# 安装依赖
pip install -r requirements.txt
```

### 步骤 4: 启动服务

```bash
# 启动文博助手服务
python -m assistant.main

# 或者使用 uvicorn
uvicorn assistant.main:app --host 0.0.0.0 --port 8400
```

看到以下输出表示启动成功：

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Starting Museum Assistant...
INFO:     Using local database: museum_assistant.db
INFO:     Skill loader initialized
INFO:     MicroAgent initialized
INFO:     Museum Assistant initialized successfully
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8400
```

### 步骤 5: 测试服务

打开新的终端窗口，运行示例客户端：

```bash
cd assistant

# 运行示例客户端
python example_client.py
```

或者使用 curl 测试：

```bash
# 基本对话
curl -X POST http://localhost:8400/chat/demo_session \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"介绍一下唐三彩\"}"
```

### 步骤 6: 访问 API 文档

在浏览器中打开：

- 服务首页：http://localhost:8400
- API 文档：http://localhost:8400/docs

## 常见问题

### Q: 提示 "OpenAI API Key 未配置"

**A:** 检查 `.env` 文件是否正确配置了 `OPENAI_API_KEY`

### Q: 提示 "端口 8400 已被占用"

**A:** 修改 `.env` 文件中的 `ASSISTANT_PORT` 为其他端口，例如 8500

### Q: 模块导入错误

**A:** 确保在 `assistant` 目录下运行命令，或者将项目路径添加到 PYTHONPATH

### Q: 数据库初始化失败

**A:** 删除 `museum_assistant.db` 文件，然后重新启动服务

## 功能测试清单

- [ ] 基本对话（介绍文物、查询展览）
- [ ] 流式输出测试
- [ ] 会话状态保存
- [ ] 会话重连
- [ ] 事件回放
- [ ] 工具调用

## 下一步

- 阅读 [README.md](README.md) 了解详细功能
- 查看 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) 了解项目架构
- 在 `agent_skills/` 目录下添加自定义技能
- 修改 `assistant_config.yaml` 配置参数

## 停止服务

在运行服务的终端按 `Ctrl + C` 停止服务
