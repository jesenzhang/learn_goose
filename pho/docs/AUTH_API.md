# Authentication API Reference

Pho 框架提供完整的用户认证和授权 API。

## Base URL

所有认证相关的 API 端点使用以下基础路径：

```
/api/v1/auth/
```

## 认证流程

### 1. 用户注册

创建新用户账户。

**Endpoint:** `POST /api/v1/auth/register`

**Request Body:**
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "secure_password",
  "display_name": "Alice",
  "role": "user"
}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| username | string | ✅ | 用户名 (3-50 字符) |
| email | string | ❌ | 邮箱地址 |
| password | string | ❌ | 密码 (6+ 字符) |
| display_name | string | ❌ | 显示名称 |
| role | string | ❌ | 用户角色 (guest/user/admin) |

**Response:** `201 Created`
```json
{
  "user_id": "user_abc123",
  "username": "alice",
  "email": "alice@example.com",
  "role": "user",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Error:** `400 Bad Request`
```json
{
  "detail": "Username 'alice' already exists"
}
```

---

### 2. 用户登录

通过用户名和密码进行认证。

**Endpoint:** `POST /api/v1/auth/login`

**Request Body:**
```json
{
  "username": "alice",
  "password": "secure_password"
}
```

**Response:** `200 OK`
```json
{
  "user_id": "user_abc123",
  "username": "alice",
  "email": "alice@example.com",
  "role": "user",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Error:** `401 Unauthorized`
```json
{
  "detail": "Invalid credentials"
}
```

---

### 3. 令牌验证

验证当前令牌是否有效。

**Endpoint:** `GET /api/v1/auth/me`

**Headers:**
```
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "user_id": "user_abc123",
  "username": "alice",
  "email": "alice@example.com",
  "display_name": "Alice",
  "role": "user",
  "is_active": true
}
```

**Error:** `401 Unauthorized`
```json
{
  "detail": "Authentication required"
}
```

---

### 4. 登出

撤销当前令牌。

**Endpoint:** `POST /api/v1/auth/logout`

**Headers:**
```
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "message": "Successfully logged out"
}
```

---

### 5. 刷新令牌

获取新的认证令牌。

**Endpoint:** `POST /api/v1/auth/refresh`

**Headers:**
```
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

## 用户管理

### 6. 获取用户信息

获取指定用户的信息（需要管理员权限）。

**Endpoint:** `GET /api/v1/auth/users/{user_id}`

**Headers:**
```
Authorization: Bearer <admin_token>
```

**Response:** `200 OK`
```json
{
  "user_id": "user_abc123",
  "username": "alice",
  "email": "alice@example.com",
  "display_name": "Alice",
  "role": "user",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 7. 列出用户

列出所有用户（需要管理员权限）。

**Endpoint:** `GET /api/v1/auth/users`

**Headers:**
```
Authorization: Bearer <admin_token>
```

**Query Parameters:**
- `limit` (optional): 返回数量限制，默认 100
- `offset` (optional): 偏移量，默认 0

**Response:** `200 OK`
```json
{
  "users": [
    {
      "user_id": "user_abc123",
      "username": "alice",
      "email": "alice@example.com",
      "role": "user",
      "is_active": true
    }
  ],
  "total": 1
}
```

---

### 8. 更新用户角色

更新用户的角色（需要管理员权限）。

**Endpoint:** `PUT /api/v1/auth/users/{user_id}/role`

**Headers:**
```
Authorization: Bearer <admin_token>
```

**Request Body:**
```json
{
  "role": "admin"
}
```

**Response:** `200 OK`
```json
{
  "user_id": "user_abc123",
  "role": "admin"
}
```

---

### 9. 停用用户

停用指定用户（需要管理员权限）。

**Endpoint:** `POST /api/v1/auth/users/{user_id}/deactivate`

**Headers:**
```
Authorization: Bearer <admin_token>
```

**Response:** `200 OK`
```json
{
  "message": "User deactivated successfully"
}
```

---

## 会话协作 API

### 10. 添加协作者

添加用户作为会话协作者。

**Endpoint:** `POST /api/v1/sessions/{session_id}/collaborators`

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "user_id": "user_xyz789",
  "role": "viewer"
}
```

**Roles:**
- `owner` - 完全控制（编辑、删除、管理协作者）
- `editor` - 编辑会话内容，不能删除
- `viewer` - 只读访问

**Response:** `200 OK`
```json
{
  "message": "Collaborator added successfully"
}
```

---

### 11. 列出协作者

列出会话的所有协作者。

**Endpoint:** `GET /api/v1/sessions/{session_id}/collaborators`

**Headers:**
```
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "collaborators": [
    {
      "user_id": "user_xyz789",
      "username": "bob",
      "display_name": "Bob",
      "role": "viewer",
      "added_at": "2024-01-15T10:30:00Z",
      "added_by": "alice"
    }
  ]
}
```

---

### 12. 移除协作者

从会话中移除协作者。

**Endpoint:** `DELETE /api/v1/sessions/{session_id}/collaborators/{user_id}`

**Headers:**
```
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "message": "Collaborator removed successfully"
}
```

---

### 13. 更新协作者角色

更新协作者的角色。

**Endpoint:** `PUT /api/v1/sessions/{session_id}/collaborators/{user_id}`

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "role": "editor"
}
```

**Response:** `200 OK`
```json
{
  "message": "Collaborator role updated successfully"
}
```

---

## 错误代码

| HTTP 状态 | 错误代码 | 描述 |
|-----------|----------|------|
| 400 | `INVALID_REQUEST` | 请求参数无效 |
| 401 | `UNAUTHORIZED` | 未认证或令牌无效 |
| 403 | `FORBIDDEN` | 权限不足 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` | 资源冲突（如用户名已存在） |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |

---

## 使用示例

### 完整认证流程

```bash
# 1. 注册新用户
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "secure_password",
    "email": "alice@example.com"
  }'

# 响应:
# {
#   "user_id": "user_abc123",
#   "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
# }

# 2. 使用令牌访问受保护的端点
curl -X GET "http://localhost:8000/api/v1/agent/sessions" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# 3. 添加会话协作者
curl -X POST "http://localhost:8000/api/v1/sessions/session_123/collaborators" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_xyz789",
    "role": "editor"
  }'
```

### Python 客户端示例

```python
import httpx

class PhoClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.token = None
        self.client = httpx.AsyncClient()

    async def register(self, username: str, password: str, email: str = None):
        """注册用户"""
        data = {"username": username, "password": password}
        if email:
            data["email"] = email

        response = await self.client.post(
            f"{self.base_url}/api/v1/auth/register",
            json=data
        )
        response.raise_for_status()

        result = response.json()
        self.token = result["token"]
        return result

    async def login(self, username: str, password: str):
        """登录"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()

        result = response.json()
        self.token = result["token"]
        return result

    async def get_sessions(self):
        """获取会话列表（需要认证）"""
        if not self.token:
            raise ValueError("Not authenticated")

        response = await self.client.get(
            f"{self.base_url}/api/v1/agent/sessions",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        response.raise_for_status()
        return response.json()

    async def add_collaborator(self, session_id: str, user_id: str, role: str):
        """添加协作者"""
        if not self.token:
            raise ValueError("Not authenticated")

        response = await self.client.post(
            f"{self.base_url}/api/v1/sessions/{session_id}/collaborators",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"user_id": user_id, "role": role}
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()

# 使用示例
async def main():
    client = PhoClient()

    # 注册
    await client.register("alice", "password123", "alice@example.com")

    # 获取会话
    sessions = await client.get_sessions()
    print(f"Sessions: {sessions}")

    # 添加协作者
    await client.add_collaborator("session_123", "user_xyz789", "viewer")

    await client.close()
```

---

## 安全建议

### 生产环境配置

1. **使用 HTTPS**
   ```python
   # 生产环境必须使用 HTTPS
   BASE_URL = "https://api.example.com"
   ```

2. **设置令牌过期时间**
   ```python
   # 在认证服务中配置
   TOKEN_EXPIRE_HOURS = 24
   ```

3. **实施速率限制**
   ```python
   from slowapi import Limiter

   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter
   ```

4. **使用环境变量存储敏感信息**
   ```bash
   export PHO_SECRET_KEY="your-secret-key"
   export PHO_DATABASE_URL="sqlite:///pho.db"
   ```
