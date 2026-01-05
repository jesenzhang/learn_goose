# src/goose/workflow/repository.py

import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .checkpointer import WorkflowCheckpointer, WorkflowCheckpoint
from goose.persistence import BaseRepository,with_table,TableSpec,PersistenceManager
from .protocol import WorkflowDefinition
import uuid
from datetime import datetime

from goose.workflow.checkpointer import WorkflowCheckpointRepository

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


WORKFLOW_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    execution_queue TEXT,   -- [变更] 存储 JSON List ["node_a", "node_b"]
    context_data TEXT,      -- JSON: 存储 node_outputs
    status TEXT,            -- running, suspended, completed, failed
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

class WorkflowDAO(BaseModel):
    id: str
    title: Optional[str] = None
    definition: WorkflowDefinition
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    

@with_table(name='workflows',model=WorkflowDAO,sql=WORKFLOW_SCHEMA,priority=0,attr_name='workflows_schema')
class WorkflowRepository(BaseRepository,WorkflowCheckpointer):
    """
    专门负责工作流状态的持久化。
    """
    def __init__(self, pm: PersistenceManager = None):
        super().__init__(pm)
        self.checkpoint_repo = WorkflowCheckpointRepository(pm)
        
    async def save(self, workflow: WorkflowDefinition, title: str) -> str:
        """Upsert Workflow (Optimized)"""
         # 1. 确保 ID 存在
        if not workflow.id:
            workflow.id = f"wf_{uuid.uuid4().hex[:8]}"
        try:
            workflow_dao = WorkflowDAO(id=workflow.id, title=title, definition=workflow)
            await self._upsert(WorkflowDAO,workflow_dao)
        except Exception as e:
            logger.error(f"Failed to upsert workflow {workflow.id}: {e}")
            raise e
        
        # # 2. [关键修复] 显式序列化
        # # 使用 model_dump(mode='json') 先转成 Python Dict，可以清晰看到存了什么
        # # 避免 model_dump_json() 在某些 Pydantic 版本下的黑盒行为
        # try:
        #     workflow_dict = workflow.model_dump(mode='json')
            
        #     # [Debug] 如果你不放心，可以在这里打印看看 nodes 是否还在
        #     # if "nodes" not in workflow_dict or not workflow_dict["nodes"]:
        #     #     logger.warning(f"⚠️ Warning: Saving workflow {workflow.id} with EMPTY nodes!")
            
        #     def_json = json.dumps(workflow_dict, ensure_ascii=False)
            
        # except Exception as e:
        #     logger.error(f"Serialization failed: {e}")
        #     raise ValueError("Failed to serialize workflow definition")

        # # 3. [优化] 使用 SQLite 的 UPSERT 语法 (INSERT OR REPLACE)
        # # 这比 "Select -> If -> Update/Insert" 更原子、更高效，且代码更少
        # sql = """
        # INSERT OR REPLACE INTO workflows (id, title, definition, updated_at) 
        # VALUES (:id, :title, :definition, CURRENT_TIMESTAMP)
        # """
        
        # await self.pm.execute(
        #     sql,
        #     {
        #         "id": workflow.id, 
        #         "title": title, 
        #         "definition": def_json
        #     }
        # )
        
        logger.info(f"💾 Workflow saved: {workflow.id} (Size: {len(workflow.model_dump_json())} chars)")
        return workflow.id

    async def get(self, wf_id: str) -> Optional[WorkflowDefinition]:
        try:
            data:WorkflowDAO = await self._get(WorkflowDAO, wf_id)
            return data.definition
        except Exception as e:
            logger.error(f"Failed to get workflow {wf_id}: {e}")
            return None
        
        # row = await self.pm.fetch_one(
        #     "SELECT definition FROM workflows WHERE id = :id",
        #     {"id": wf_id}
        # )
        # if row and row.get("definition"):
        #     try:
        #         # 反序列化 JSON -> WorkflowDefinition
        #         data = json.loads(row["definition"])
        #         return WorkflowDefinition.model_validate(data)
        #     except Exception as e:
        #         logger.error(f"Failed to parse workflow {wf_id}: {e}")
        # return None
    
    async def get_batch(self, wf_ids: List[str]) -> List[WorkflowDefinition]:
        if not wf_ids: return []
        
        data_list:List[WorkflowDAO] = await self._get_batch(WorkflowDAO, wf_ids)
        
        return [data.definition for data in data_list]
        
        # # 动态构建 SQL: SELECT * FROM workflows WHERE id IN ('id1', 'id2', ...)
        # placeholders = ",".join([f":id{i}" for i in range(len(wf_ids))])
        # params = {f"id{i}": wid for i, wid in enumerate(wf_ids)}
        
        # sql = f"SELECT id, title, updated_at FROM workflows WHERE id IN ({placeholders})"
        
        # rows = await self.pm.fetch_all(sql, params)
        # # 保持顺序 (可选)
        # return [dict(r) for r in rows]
    
    async def list(self, limit: int, offset: int) -> List[WorkflowDefinition]:
        """列出工作流摘要"""
        data_list:List[WorkflowDAO]  = await self._list(WorkflowDAO, sort_key="updated_at", limit=limit, offset=offset)
        return [data.definition for data in data_list]
        
        # sql = "SELECT id, title, created_at, updated_at FROM workflows ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
        # rows = await self.pm.fetch_all(sql, {"limit": limit, "offset": offset})
        # return [dict(r) for r in rows]
    
    async def save_checkpoint(self, state: WorkflowCheckpoint):
        """保存状态"""
        try:
            await self.checkpoint_repo.save_checkpoint(state)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise e
        # # 1. 序列化
        # queue_json = json.dumps(state.execution_queue)
        # context_json = json.dumps(state.context_data)
        
        # # 2. SQL 包含 execution_queue
        # # [修改点 1] 使用 :key 风格的占位符
        # sql = """
        # INSERT OR REPLACE INTO workflow_runs 
        # (run_id, execution_queue, context_data, status, error, updated_at)
        # VALUES (:run_id, :execution_queue, :context_data, :status, :error, CURRENT_TIMESTAMP)
        # """
        
        # try:
        #     # 3. 执行
        #     # [修改点 2] 传入字典 (Dict)，而不是元组 (Tuple)
        #     await self.pm.execute(
        #         sql, 
        #         {
        #             "run_id": state.run_id,
        #             "execution_queue": queue_json,
        #             "context_data": context_json,
        #             "status": state.status,
        #             "error": state.error
        #         }
        #     )
        # except Exception as e:
        #     # [关键] 必须把错误打印出来！
        #     # 建议使用 logger.error 而不是 print
        #     logger.error(f"❌ FATAL ERROR: Database Save Failed! Reason: {e}")
        #     raise e  # 抛出异常，让 Scheduler 知道出事了

    async def load_checkpoint(self, run_id: str) -> Optional[WorkflowCheckpoint]:
        """加载状态"""
        return await self.checkpoint_repo.load_checkpoint(run_id)
        # # [风格适配] 使用 :key 占位符
        # sql = "SELECT * FROM workflow_runs WHERE run_id = :run_id"
        
        # try:
        #     # [优化] 使用 fetch_one，直接获取单行字典
        #     # 参数传递使用字典 {"run_id": run_id}
        #     row = await self.pm.fetch_one(sql, {"run_id": run_id})
        # except Exception as e:
        #     logger.error(f"❌ FATAL ERROR: Database Query Failed! Reason: {e}")
        #     raise e
        
        # if not row:
        #     return None
            
        # # --- 反序列化处理 (增强健壮性) ---
        
        # # 1. 处理 Execution Queue
        # queue = []
        # raw_queue = row.get("execution_queue")
        
        # # 兼容旧数据：检查 current_node_id
        # if raw_queue is None:
        #      old_node_id = row.get("current_node_id")
        #      if old_node_id:
        #          queue = [old_node_id]
        # else:
        #     try:
        #         # 只有当 raw_queue 是字符串时才解析
        #         if isinstance(raw_queue, str):
        #             queue = json.loads(raw_queue)
        #         # 如果已经是 list (某些特殊 driver 行为)，直接用
        #         elif isinstance(raw_queue, list):
        #             queue = raw_queue
        #     except Exception:
        #         logger.warning(f"Failed to parse execution_queue for {run_id}, resetting.")
        #         queue = []

        # # 2. 处理 Context Data
        # context_data = {}
        # raw_context = row.get("context_data")
        
        # if raw_context:
        #     try:
        #         if isinstance(raw_context, str):
        #             context_data = json.loads(raw_context)
        #         elif isinstance(raw_context, dict):
        #             context_data = raw_context
        #     except Exception:
        #         logger.warning(f"Failed to parse context_data for {run_id}, resetting.")
        #         context_data = {}

        # return WorkflowCheckpoint(
        #     run_id=row["run_id"],
        #     execution_queue=queue,
        #     context_data=context_data,
        #     status=row["status"],
        #     error=row.get("error")
        # )