import json
import logging
from typing import Dict, Any, Optional, List
from goose.persistence import BaseRepository,TableSpec,with_table
from .types import Execution,ExecutionStatus

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
    created_at REAL,
    updated_at REAL
);
"""

# 索引：用于列表查询加速
EXECUTION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_exec_wf_id ON executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_exec_created_at ON executions(created_at);
"""

@with_table(name='executions', sql=[EXECUTION_SCHEMA,EXECUTION_INDEX], model=Execution,priority=0,attr_name='executions_spec')
class ExecutionRepository(BaseRepository):

    async def create(self, run_id: str, workflow_id: str, inputs: Dict[str, Any], title: str = ""):
        """[Start] 创建初始记录"""
        try:
            # 1. 构造 Entity (Python 生成时间，inputs 还是 dict)
            execution = Execution(
                id=run_id,
                workflow_id=workflow_id,
                title=title,
                inputs=inputs,
                status=ExecutionStatus.PENDING,
                # created_at 由 Pydantic default_factory 自动生成 (float)
            )
            
            # 2. 调用通用插入
            # BaseRepository 会自动处理:
            # - inputs (dict) -> JSON String
            # - status (Enum) -> String
            await self._insert(Execution, execution)
            
            return execution
        except Exception as e:
            logger.error(f"Failed to create execution: {e}")
            raise
    
        # await self.pm.execute(
        #     """
        #     INSERT INTO executions (id, workflow_id, title, status, inputs, created_at)
        #     VALUES (:id, :wf_id, :title, 'pending', :inputs, CURRENT_TIMESTAMP)
        #     """,
        #     {
        #         "id": run_id,
        #         "wf_id": workflow_id,
        #         "title": title,
        #         "inputs": json.dumps(inputs)
        #     }
        # )
    async def list(self, workflow_id: str, limit: int=-1, offset: int=0) -> List[Execution]:
        # 使用通用查询接口
        # 兼容 SQL (WHERE workflow_id=...) 和 JSONL (filter)
        execs:List[Execution] = await self._find(
            Execution,
            filters={"workflow_id": workflow_id},
            limit=limit,
            offset=offset
        )
        
        # 内存排序 (为了保险，特别是 JSONL 模式)
        # 假设前端需要按创建时间倒序 (最新的在最前)
        execs.sort(key=lambda x: x.created_at, reverse=True)
        
        return execs
        # sql = """
        #     SELECT * FROM executions 
        #     WHERE workflow_id = :wf_id 
        #     ORDER BY created_at DESC 
        #     LIMIT :limit OFFSET :offset
        # """
        # rows = await self.pm.fetch_all(sql, {"wf_id": workflow_id, "limit": limit, "offset": offset})
        # return [dict(r) for r in rows]

    async def get(self, run_id: str) -> Optional[Execution]:
        results = await self._find(Execution, filters={"id": run_id}, limit=1)
        return results[0] if results else None
    
    async def update_status(self, run_id: str, status: str, outputs: Any = None, error: str = None):
        """[Sync] 根据引擎事件更新状态"""
        # 1. 准备要更新的字段
        updates = {
            "status": status,
            "updated_at": time.time()  # 显式更新时间
        }
        
        # 2. 动态添加可选字段
        if outputs is not None:
            # 直接传 dict/list 即可，_update_by 会自动序列化
            updates["outputs"] = outputs
            
            # 💡 自动计算耗时 (Optional 优化)
            # 如果你有开始时间，这里可以计算 duration
            # 但通常需要先查出来，或者由上层传入 start_time
            # 这里简单处理，暂不计算，或仅记录结束时间

        if error is not None:
            updates["error"] = error

        # 3. 调用通用批量更新接口
        # 这会生成 UPDATE executions SET ... WHERE id = :run_id
        await self._update_by(
            Execution,
            filters={"id": run_id},
            **updates
        )

    async def list_pagination(self, wf_id: str, page: int, page_size: int) -> List[Execution]:
        """
        [Query] 分页查询
        """
        offset = (page - 1) * page_size
        
        # 使用通用查询接口
        # 兼容 SQL (WHERE workflow_id=...) 和 JSONL (filter)
        execs:List[Execution] = await self._find(
            Execution,
            filters={"workflow_id": wf_id},
            limit=page_size,
            offset=offset
        )
        
        # 内存排序 (为了保险，特别是 JSONL 模式)
        # 假设前端需要按创建时间倒序 (最新的在最前)
        execs.sort(key=lambda x: x.created_at, reverse=True)
        
        return execs