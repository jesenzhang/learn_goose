# src/goose/workflow/repository.py

import json
import logging
from typing import Optional, List, Dict, Any
from .persistence import WorkflowCheckpointer, WorkflowState
from goose.persistence.manager import persistence_manager
from .protocol import WorkflowDefinition
import uuid

logger = logging.getLogger(__name__)


# --- 1. 定义 Workflow 表结构 ---

# --- Schemas ---
WORKFLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    title TEXT,
    definition TEXT, -- JSON structure
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# 注意：run_id 是外键，关联到 sessions(id)
WORKFLOW_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    execution_queue TEXT,   -- [变更] 存储 JSON List ["node_a", "node_b"]
    context_data TEXT,      -- JSON: 存储 node_outputs
    status TEXT,            -- running, suspended, completed, failed
    error TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def register_workflow_schemas():
    """向 PersistenceManager 注册表结构"""
    persistence_manager.register_schema(WORKFLOW_SCHEMA)
    persistence_manager.register_schema(WORKFLOW_RUNS_SCHEMA)

class WorkflowRepository(WorkflowCheckpointer):
    """
    专门负责工作流状态的持久化。
    """
    def __init__(self):
        register_workflow_schemas()
        self.pm =persistence_manager

    async def save(self, workflow: WorkflowDefinition, title: str) -> str:
        """Upsert Workflow"""
        # 如果 ID 不存在，生成新的
        if not workflow.id:
            workflow.id = f"wf_{uuid.uuid4().hex[:8]}"
        
        # 序列化
        def_json = workflow.model_dump_json()
        
        # 检查是否存在 (简单做法，生产环境可用 Upsert 语法)
        exists = await self.pm.fetch_one(
            "SELECT id FROM workflows WHERE id = :id", 
            {"id": workflow.id}
        )
        
        if exists:
            await self.pm.execute(
                """
                UPDATE workflows 
                SET title = :title, definition = :definition, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                {"id": workflow.id, "title": title, "definition": def_json}
            )
        else:
            await self.pm.execute(
                """
                INSERT INTO workflows (id, title, definition) 
                VALUES (:id, :title, :definition)
                """,
                {"id": workflow.id, "title": title, "definition": def_json}
            )
        
        return workflow.id

    async def get(self, wf_id: str) -> Optional[WorkflowDefinition]:
        row = await self.pm.fetch_one(
            "SELECT definition FROM workflows WHERE id = :id",
            {"id": wf_id}
        )
        if row and row.get("definition"):
            try:
                # 反序列化 JSON -> WorkflowDefinition
                data = json.loads(row["definition"])
                return WorkflowDefinition.model_validate(data)
            except Exception as e:
                logger.error(f"Failed to parse workflow {wf_id}: {e}")
        return None
    
    async def get_batch(self, wf_ids: List[str]) -> List[Dict]:
        if not wf_ids: return []
        
        # 动态构建 SQL: SELECT * FROM workflows WHERE id IN ('id1', 'id2', ...)
        placeholders = ",".join([f":id{i}" for i in range(len(wf_ids))])
        params = {f"id{i}": wid for i, wid in enumerate(wf_ids)}
        
        sql = f"SELECT id, title, updated_at FROM workflows WHERE id IN ({placeholders})"
        
        rows = await self.pm.fetch_all(sql, params)
        # 保持顺序 (可选)
        return [dict(r) for r in rows]
    
    async def list(self, limit: int, offset: int) -> List[Dict[str, Any]]:
        """列出工作流摘要"""
        sql = "SELECT id, title, created_at, updated_at FROM workflows ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
        rows = await self.pm.fetch_all(sql, {"limit": limit, "offset": offset})
        return [dict(r) for r in rows]
    
    async def save_checkpoint(self, state: WorkflowState):
        """保存状态"""
        # 1. 序列化
        queue_json = json.dumps(state.execution_queue)
        context_json = json.dumps(state.context_data)
        
        # 2. SQL 包含 execution_queue
        # [修改点 1] 使用 :key 风格的占位符
        sql = """
        INSERT OR REPLACE INTO workflow_runs 
        (run_id, execution_queue, context_data, status, error, updated_at)
        VALUES (:run_id, :execution_queue, :context_data, :status, :error, CURRENT_TIMESTAMP)
        """
        
        try:
            # 3. 执行
            # [修改点 2] 传入字典 (Dict)，而不是元组 (Tuple)
            await self.pm.execute(
                sql, 
                {
                    "run_id": state.run_id,
                    "execution_queue": queue_json,
                    "context_data": context_json,
                    "status": state.status,
                    "error": state.error
                }
            )
        except Exception as e:
            # [关键] 必须把错误打印出来！
            # 建议使用 logger.error 而不是 print
            logger.error(f"❌ FATAL ERROR: Database Save Failed! Reason: {e}")
            raise e  # 抛出异常，让 Scheduler 知道出事了

    async def load_checkpoint(self, run_id: str) -> Optional[WorkflowState]:
        """加载状态"""
        
        # [风格适配] 使用 :key 占位符
        sql = "SELECT * FROM workflow_runs WHERE run_id = :run_id"
        
        try:
            # [优化] 使用 fetch_one，直接获取单行字典
            # 参数传递使用字典 {"run_id": run_id}
            row = await self.pm.fetch_one(sql, {"run_id": run_id})
        except Exception as e:
            logger.error(f"❌ FATAL ERROR: Database Query Failed! Reason: {e}")
            raise e
        
        if not row:
            return None
            
        # --- 反序列化处理 (增强健壮性) ---
        
        # 1. 处理 Execution Queue
        queue = []
        raw_queue = row.get("execution_queue")
        
        # 兼容旧数据：检查 current_node_id
        if raw_queue is None:
             old_node_id = row.get("current_node_id")
             if old_node_id:
                 queue = [old_node_id]
        else:
            try:
                # 只有当 raw_queue 是字符串时才解析
                if isinstance(raw_queue, str):
                    queue = json.loads(raw_queue)
                # 如果已经是 list (某些特殊 driver 行为)，直接用
                elif isinstance(raw_queue, list):
                    queue = raw_queue
            except Exception:
                logger.warning(f"Failed to parse execution_queue for {run_id}, resetting.")
                queue = []

        # 2. 处理 Context Data
        context_data = {}
        raw_context = row.get("context_data")
        
        if raw_context:
            try:
                if isinstance(raw_context, str):
                    context_data = json.loads(raw_context)
                elif isinstance(raw_context, dict):
                    context_data = raw_context
            except Exception:
                logger.warning(f"Failed to parse context_data for {run_id}, resetting.")
                context_data = {}

        return WorkflowState(
            run_id=row["run_id"],
            execution_queue=queue,
            context_data=context_data,
            status=row["status"],
            error=row.get("error")
        )