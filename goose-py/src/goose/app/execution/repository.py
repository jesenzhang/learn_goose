import json
import logging
from typing import Dict, Any, Optional, List
from goose.persistence import persistence_manager

logger = logging.getLogger("goose.server.execution.repo")

# --- Business Layer Schema ---
# 这张表只存业务关心的字段：输入、输出、状态、时间、谁跑的
EXECUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,        -- run_id
    workflow_id TEXT,
    title TEXT,                 -- 任务标题 (Snapshotted)
    status TEXT,                -- pending, running, completed, failed
    inputs TEXT,                -- JSON: 初始输入
    outputs TEXT,               -- JSON: 最终结果
    error TEXT,                 -- 错误信息
    duration REAL,              -- 耗时 (秒)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# 索引：用于列表查询加速
EXECUTION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_exec_wf_id ON executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_exec_created_at ON executions(created_at);
"""

class ExecutionRepository:
    def __init__(self):
        self.pm = persistence_manager
        self.pm.register_schema(EXECUTION_SCHEMA)
        self.pm.register_schema(EXECUTION_INDEX)

    async def create(self, run_id: str, workflow_id: str, inputs: Dict[str, Any], title: str = ""):
        """[Start] 创建初始记录"""
        await self.pm.execute(
            """
            INSERT INTO executions (id, workflow_id, title, status, inputs, created_at)
            VALUES (:id, :wf_id, :title, 'pending', :inputs, CURRENT_TIMESTAMP)
            """,
            {
                "id": run_id,
                "wf_id": workflow_id,
                "title": title,
                "inputs": json.dumps(inputs)
            }
        )
    async def list(self, workflow_id: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        sql = """
            SELECT * FROM executions 
            WHERE workflow_id = :wf_id 
            ORDER BY created_at DESC 
            LIMIT :limit OFFSET :offset
        """
        rows = await self.pm.fetch_all(sql, {"wf_id": workflow_id, "limit": limit, "offset": offset})
        return [dict(r) for r in rows]

    async def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        row = await self.pm.fetch_one("SELECT * FROM executions WHERE id = :id", {"id": run_id})
        if row:
            data = dict(row)
            # 简单反序列化
            for key in ['inputs', 'outputs']:
                if isinstance(data.get(key), str):
                    try: data[key] = json.loads(data[key])
                    except: pass
            return data
        return None
    
    async def update_status(self, run_id: str, status: str, outputs: Dict = None, error: str = None):
        """[Sync] 根据引擎事件更新状态"""
        updates = ["status = :status", "updated_at = CURRENT_TIMESTAMP"]
        params = {"run_id": run_id, "status": status}
        
        if outputs is not None:
            updates.append("outputs = :outputs")
            params["outputs"] = json.dumps(outputs)
            
        if error is not None:
            updates.append("error = :error")
            params["error"] = error
            
        sql = f"UPDATE executions SET {', '.join(updates)} WHERE id = :run_id"
        await self.pm.execute(sql, params)

    async def list_pagination(self, wf_id: str, page: int, page_size: int):
        offset = (page - 1) * page_size
        sql = """
            SELECT * FROM executions 
            WHERE workflow_id = :wf_id 
            ORDER BY created_at DESC 
            LIMIT :limit OFFSET :offset
        """
        rows = await self.pm.fetch_all(sql, {"wf_id": wf_id, "limit": page_size, "offset": offset})
        return [dict(r) for r in rows]