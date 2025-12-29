# src/goose/workflow/repository.py

import json
import logging
from typing import Optional
from ..persistence import PersistenceManager
from .persistence import WorkflowCheckpointer, WorkflowState

logger = logging.getLogger(__name__)

# --- 1. 定义 Workflow 表结构 ---
# 注意：run_id 是外键，关联到 sessions(id)
WORKFLOW_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    execution_queue TEXT,   -- [变更] 存储 JSON List ["node_a", "node_b"]
    context_data TEXT,      -- JSON: 存储 node_outputs
    status TEXT,            -- running, suspended, completed, failed
    error TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(run_id) REFERENCES sessions(id)
);
"""

def register_workflow_schemas():
    """向 PersistenceManager 注册表结构"""
    pm = PersistenceManager.get_instance()
    pm.register_schema(WORKFLOW_RUNS_SCHEMA)

class WorkflowRepository(WorkflowCheckpointer):
    """
    专门负责工作流状态的持久化。
    """
    def __init__(self):
        register_workflow_schemas()
        self.pm = PersistenceManager.get_instance()

    async def save_checkpoint(self, state: WorkflowState):
        """保存状态"""
        # 1. 序列化
        queue_json = json.dumps(state.execution_queue)
        context_json = json.dumps(state.context_data)
        
        # 2. SQL 包含 execution_queue
        sql = """
        INSERT OR REPLACE INTO workflow_runs 
        (run_id, execution_queue, context_data, status, error, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        
        try:
            # 3. 执行
            await self.pm.execute(
                sql, 
                (state.run_id, queue_json, context_json, state.status, state.error)
            )
        except Exception as e:
            # [关键] 必须把错误打印出来！
            print(f"❌ FATAL ERROR: Database Save Failed! Reason: {e}")
            raise e  # 抛出异常，让 Scheduler 知道出事了

    async def load_checkpoint(self, run_id: str) -> Optional[WorkflowState]:
        """加载状态"""
        
        sql = "SELECT * FROM workflow_runs WHERE run_id = ?"
        try:
            rows = await self.pm.fetch_all(sql, (run_id,))
        except Exception as e:
            print(f"❌ FATAL ERROR: Database Query Failed! Reason: {e}")
            raise e
        
        if not rows:
            return None
            
        row = rows[0] # 假设返回的是 dict 或 sqlite3.Row
        
        # 3. 反序列化 JSON String -> List/Dict
        try:
            # 兼容：如果字段名为 current_node_id (旧表) 还是 execution_queue (新表)
            # 这里假设你已经更新了表结构，或者做了迁移
            raw_queue = row.get("execution_queue")
            if raw_queue:
                queue = json.loads(raw_queue)
            else:
                # 兼容旧数据：如果数据库里存的是旧的单点 ID，把它变成列表
                old_node_id = row.get("current_node_id")
                queue = [old_node_id] if old_node_id else []
        except Exception:
            queue = []

        try:
            context_data = json.loads(row.get("context_data", "{}"))
        except:
            context_data = {}

        return WorkflowState(
            run_id=row["run_id"], # 或者 row[0] 取决于 driver
            execution_queue=queue,
            context_data=context_data,
            status=row["status"],
            error=row.get("error")
        )