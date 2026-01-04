import json
from goose.persistence import persistence_manager
from typing import Optional,Dict,Any,List
# 新增 User Schema
USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    api_key TEXT,         -- 用于 API 调用鉴权
    config TEXT,          -- 用户级全局配置 (JSON)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# Repository 实现
class UserRepository:
    def __init__(self):
        self.pm = persistence_manager
        self.pm.register_schema(USER_SCHEMA)

    async def get_by_id(self, user_id: str) -> Optional[Dict]:
        return await self.pm.fetch_one("SELECT * FROM users WHERE id = :id", {"id": user_id})

    async def get_by_api_key(self, api_key: str) -> Optional[Dict]:
        return await self.pm.fetch_one("SELECT * FROM users WHERE api_key = :key", {"key": api_key})
    
    # create 方法需要稍微修改以支持 api_key 和 config
    async def create(self, user_id: str, username: str, api_key: str, config: Dict = None):
        import json
        sql = """
        INSERT INTO users (id, username, api_key, config) 
        VALUES (:id, :name, :key, :cfg)
        """
        await self.pm.execute(sql, {
            "id": user_id, 
            "name": username, 
            "key": api_key,
            "cfg": json.dumps(config or {})
        })
        
    async def update_field(self, user_id: str, field: str, value: Any):
        """[Generic] 更新单个字段"""
        # 注意：field不能直接作为参数化查询的key，需要拼接字符串 (但在内部受控调用是安全的)
        allowed_fields = ["api_key", "config", "username"]
        if field not in allowed_fields:
            raise ValueError(f"Field {field} is not updatable")
            
        sql = f"UPDATE users SET {field} = :val, updated_at = CURRENT_TIMESTAMP WHERE id = :id"
        await self.pm.execute(sql, {"val": value, "id": user_id})

    
        
        
USER_RESOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
    user_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,          -- 枚举: 'workflow', 'execution', 'file'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 联合索引，加速查询 "某个用户的所有工作流"
    UNIQUE(user_id, resource_id, resource_type)
);
"""
# 索引：加速反向查询 "这个资源属于谁"
USER_RESOURCE_INDEX = "CREATE INDEX IF NOT EXISTS idx_res_id ON user_resources(resource_id);"

class UserResourceRepository:
    """
    专门负责管理 User <-> Resource 的绑定关系
    """
    def __init__(self):
        self.pm = persistence_manager
        self.pm.register_schema(USER_RESOURCE_SCHEMA)
        self.pm.register_schema(USER_RESOURCE_INDEX)

    async def bind(self, user_id: str, resource_id: str, resource_type: str):
        """[Link] 绑定资源给用户"""
        await self.pm.execute(
            """
            INSERT OR IGNORE INTO user_resources (user_id, resource_id, resource_type)
            VALUES (:uid, :rid, :type)
            """,
            {"uid": user_id, "rid": resource_id, "type": resource_type}
        )
        
    async def unbind(self, user_id: str, resource_id: str):
        """[Unlink] 解除绑定"""
        await self.pm.execute(
            "DELETE FROM user_resources WHERE user_id=:uid AND resource_id=:rid",
            {"uid": user_id, "rid": resource_id}
        )
        
    async def get_resource_ids(self, user_id: str, resource_type: str, limit: int, offset: int) -> List[str]:
        """[Query] 获取用户拥有的资源 ID 列表"""
        rows = await self.pm.fetch_all(
            """
            SELECT resource_id FROM user_resources 
            WHERE user_id = :uid AND resource_type = :type
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"uid": user_id, "type": resource_type, "limit": limit, "offset": offset}
        )
        return [r["resource_id"] for r in rows]

    async def check_ownership(self, user_id: str, resource_id: str) -> bool:
        """[Auth] 检查是否有权访问"""
        row = await self.pm.fetch_one(
            "SELECT 1 FROM user_resources WHERE user_id=:uid AND resource_id=:rid",
            {"uid": user_id, "rid": resource_id}
        )
        return bool(row)