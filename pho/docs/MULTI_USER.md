# Multi-User Support

Pho 框架提供完整的多用户支持，包括用户认证、授权、会话隔离和协作功能。

**重要**: 多用户支持是系统原生功能，新建数据库时会自动创建所有必需的表结构，无需手动迁移。

## 架构概览

### 数据模型

```
┌─────────────────────────────────────────────────────────────┐
│                        users 表                            │
│  ┌──────────────┬─────────────┬─────────────┐              │
│  │ id (PK)      │ username    │ role        │              │
│  └──────────────┴─────────────┴─────────────┘              │
└─────────────────────────────────────────────────────────────┘
                          │ 1:N
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       sessions 表                          │
│  ┌──────────────┬─────────────┬─────────────┐              │
│  │ id (PK)      │ user_id (FK)│  ...        │              │
│  └──────────────┴─────────────┴─────────────┘              │
└─────────────────────────────────────────────────────────────┘
                          │ 1:N
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       messages 表                           │
│  ┌──────────────┬─────────────┬─────────────┐              │
│  │ id (PK)      │ user_id (FK)│  ...        │              │
│  └──────────────┴─────────────┴─────────────┘              │
└─────────────────────────────────────────────────────────────┘
                          │ 1:N
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   workflow_checkpoints 表                   │
│  ┌──────────────┬──────────────────┬──────────────────┐     │
│  │ run_id (PK)  │ session_id (FK)  │  ...              │     │
│  └──────────────┴──────────────────┴──────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                          │ 1:N
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     workflow_events 表                      │
│  ┌──────────────┬─────────────┬─────────────┐              │
│  │ id (PK)      │ user_id (FK)│  ...        │              │
│  └──────────────┴─────────────┴─────────────┘              │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ N:M (协作支持)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 session_collaborators 表                    │
│  ┌──────────────┬─────────────┬─────────────┐              │
│  │ session_id   │ user_id     │ role        │              │
│  └──────────────┴─────────────┴─────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### 设计原则

1. **用户隔离** - 每个用户只能访问自己的会话和数据
2. **协作支持** - 通过 `session_collaborators` 表支持多用户协作
3. **间接关联** - 工作流通过 session_id 间接关联用户
4. **索引优化** - 为所有用户相关查询添加索引
5. **原生设计** - 多用户支持是系统原生功能，无需迁移

### 数据库表结构

多用户支持由以下表组成（在首次启动时自动创建）：

| 表名 | 优先级 | 说明 |
|------|--------|------|
| `users` | -10 | 用户基础信息 |
| `session_collaborators` | 0 | 会话协作关系 |
| `sessions` | 0 | 会话（含 user_id 字段） |
| `messages` | 1 | 消息（含 user_id 字段） |
| `workflow_events` | N | 工作流事件（含 user_id 字段） |
| `workflow_checkpoints` | N | 工作流检查点（含 session_id 字段） |

## 用户角色与权限

### 角色定义

| 角色 | 描述 | 权限 |
|------|------|------|
| `GUEST` | 访客 | 只读访问 |
| `USER` | 普通用户 | 读写权限 |
| `ADMIN` | 管理员 | 完全权限 |

### 权限矩阵

| 操作 | GUEST | USER | ADMIN |
|------|-------|------|-------|
| 查看会话 | ✅ | ✅ | ✅ |
| 创建会话 | ❌ | ✅ | ✅ |
| 编辑会话 | ❌ | ✅ | ✅ |
| 删除会话 | ❌ | ✅ (仅自己的) | ✅ |
| 管理用户 | ❌ | ❌ | ✅ |
| 查看所有会话 | ❌ | ❌ | ✅ |

### 协作者角色

| 角色 | 说明 | 权限 |
|------|------|------|
| `viewer` | 查看者 | 只读访问会话 |
| `editor` | 编辑者 | 可编辑会话内容 |
| `owner` | 所有者 | 完全控制，包括管理协作者 |

## 认证服务

### 创建用户

```python
from pho.auth import CreateUserRequest, get_user_repository

user_repo = get_user_repository()

request = CreateUserRequest(
    username="alice",
    email="alice@example.com",
    password="secure_password",
    display_name="Alice",
    role=UserRole.USER
)

user = await user_repo.create_user(request)
print(f"Created user: {user.id}")
```

### 认证登录

```python
from pho.auth import get_auth_service

auth_service = get_auth_service()

# 通过用户名密码认证
user = await auth_service.authenticate_by_credentials(
    username="alice",
    password="secure_password"
)

if user:
    # 创建认证令牌
    token = await auth_service.create_token(user.id)
    print(f"Token: {token}")
```

### 令牌验证

```python
# 在 API 请求中验证令牌
user = await auth_service.authenticate_by_token(token)
if user:
    print(f"Authenticated as: {user.username}")
    print(f"Role: {user.role}")
    print(f"Has write permission: {user.can_write()}")
```

## 会话管理

### 创建用户会话

```python
from pho.session import SessionRepository
from pho.auth import UserRole
import time

session_repo = SessionRepository()

session = Session(
    id="session_123",
    name="My Session",
    working_dir="/workspace",
    user_id="user_alice",  # 关联用户
    created_at=time.time(),
    updated_at=time.time()
)

await session_repo.create_session(session)
```

### 查询用户会话

```python
# 获取用户的所有会话
sessions = await session_repo.list_sessions_for_user(
    user_id="user_alice",
    limit=10
)

# 获取用户会话统计
count = await session_repo.get_user_session_count("user_alice")
print(f"User has {count} sessions")
```

## 会话协作

### 添加协作者

```python
from pho.auth import get_collaborator_repository

collab_repo = get_collaborator_repository()

# 添加 Bob 为 Alice 会话的查看者
await collab_repo.add_collaborator(
    session_id="session_123",
    user_id="user_bob",
    role="viewer",
    added_by="user_alice"
)

# 添加为编辑者
await collab_repo.add_collaborator(
    session_id="session_123",
    user_id="user_charlie",
    role="editor",
    added_by="user_alice"
)
```

### 列出协作者

```python
# 获取会话的所有协作者
collaborators = await collab_repo.list_collaborators("session_123")

for collab in collaborators:
    print(f"{collab.user_id}: {collab.role}")

# 检查访问权限
has_access = await session_repo.is_session_accessible(
    session_id="session_123",
    user_id="user_bob"
)
print(f"Bob can access: {has_access}")
```

### 移除协作者

```python
await collab_repo.remove_collaborator(
    session_id="session_123",
    user_id="user_bob"
)
```

## API 使用

### 启动服务时初始化数据库

```python
from pho.persistence import init_persistence

# 初始化持久化层（自动创建所有表）
pm = init_persistence("sqlite:///pho.db")
await pm.boot()

# 数据库已准备好，包含所有多用户表
```

### 获取用户统计

```python
from pho.auth import get_user_repository

user_repo = get_user_repository()

# 获取用户总数
total_users = await user_repo.count_users()

# 列出所有用户
users = await user_repo.list_users(limit=100)
for user in users:
    print(f"{user.username} ({user.role})")
```

## FastAPI 集成

### 添加认证中间件

```python
from fastapi import FastAPI
from pho.api.auth_middleware import AuthenticationMiddleware

app = FastAPI()
app.add_middleware(AuthenticationMiddleware)
```

### 保护路由

```python
from pho.api.auth_middleware import get_required_user
from pho.auth import AuthUser

@router.get("/sessions")
async def list_sessions(user: AuthUser = Depends(get_required_user)):
    # user.id 包含已认证用户的 ID
    sessions = await session_repo.list_sessions_for_user(user.id)
    return {"sessions": sessions}
```

## 完整示例

### 设置多用户系统

```python
import asyncio
from pho.persistence import init_persistence
from pho.auth import (
    CreateUserRequest, UserRole,
    get_user_repository, get_auth_service
)
from pho.session import SessionRepository

async def setup_multiuser():
    # 1. 初始化数据库（自动创建所有表）
    pm = init_persistence("sqlite:///pho.db")
    await pm.boot()

    # 2. 创建用户
    user_repo = get_user_repository()
    alice = await user_repo.create_user(CreateUserRequest(
        username="alice",
        email="alice@example.com",
        password="password123",
        role=UserRole.USER
    ))

    # 3. 认证并获取令牌
    auth_service = get_auth_service()
    token = await auth_service.create_token(alice.id)

    # 4. 创建用户会话
    session_repo = SessionRepository()
    await session_repo.create_session(Session(
        id="session_123",
        name="Alice's Session",
        working_dir="/workspace",
        user_id=alice.id,
        created_at=time.time(),
        updated_at=time.time()
    ))

    print(f"✅ Multi-user setup complete!")
    print(f"   User: {alice.username}")
    print(f"   Token: {token}")
    print(f"   Session: session_123")

asyncio.run(setup_multiuser())
```

## 数据持久化架构

### UserRepository

基于 `BaseRepository`，提供：
- `create_user()` - 创建用户
- `get_user_by_id()` - 按 ID 获取
- `get_user_by_username()` - 按用户名获取
- `get_user_by_email()` - 按邮箱获取
- `list_users()` - 列出用户
- `update_user()` - 更新用户信息
- `verify_password()` - 验证密码
- `change_password()` - 修改密码

### SessionCollaboratorRepository

基于 `BaseRepository`，提供：
- `add_collaborator()` - 添加协作者
- `remove_collaborator()` - 移除协作者
- `list_collaborators()` - 列出协作者
- `is_collaborator()` - 检查是否是协作者
- `get_collaborator_role()` - 获取协作者角色

### SessionRepository

扩展方法（多用户支持）：
- `list_sessions_for_user()` - 列出用户会话
- `get_user_session_count()` - 获取用户会话数
- `list_accessible_sessions()` - 列出可访问会话（自有+协作）
- `is_session_accessible()` - 检查会话访问权限
