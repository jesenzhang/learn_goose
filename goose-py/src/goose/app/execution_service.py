# src/goose/app/execution/service.py

import uuid
import logging
from typing import Dict, Any, AsyncGenerator, List, Optional

from goose.workflow.converter import WorkflowConverter
from goose.user.repository import UserResourceRepository
from goose.execution.repository import ExecutionRepository
from goose.workflow.repository import WorkflowRepository
from goose.session.repository import SessionRepository

# 引入 Manager
from goose.execution.manager import ExecutionManager

logger = logging.getLogger("goose.app.execution")

class ExecutionService:
    """
    【职责】业务逻辑门面 (无状态)
    1. 鉴权 (Auth)
    2. 数据库操作 (CRUD)
    3. 准备数据 (Graph Building)
    4. 指挥 Manager
    """
    def __init__(
        self, 
        manager: ExecutionManager, # 依赖注入 Manager
        converter: WorkflowConverter,
        wf_repo: WorkflowRepository,
        exec_repo: ExecutionRepository,
        auth_repo: UserResourceRepository,
        session_repo: SessionRepository
    ):
        self.manager = manager
        self.converter = converter
        self.wf_repo = wf_repo
        self.exec_repo = exec_repo
        self.auth_repo = auth_repo
        self.session_repo = session_repo

    # ==========================================
    # 1. 执行控制 (Start / Resume / Stream)
    # ==========================================

    async def run_workflow(
        self, 
        wf_id: str, 
        inputs: Dict[str, Any], 
        user_id: str
    ) -> str:
        """[Async] 仅触发执行，返回 run_id (Fire & Forget)"""
        # 1. 鉴权 & 创建记录
        run_id = await self._prepare_new_run(wf_id, inputs, user_id)
        
        # 2. 准备图
        graph = await self._load_graph(wf_id)
        
        # 3. 委托 Manager 运行
        await self.manager.start_execution(run_id, graph, inputs, user_id, is_resume=False)
        
        return run_id

    async def execute_stream_generator(
        self, 
        wf_id: str, 
        inputs: Dict[str, Any], 
        user_id: str,
        after_seq_id: int = -1
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 启动新任务并监听流"""
        # 1. 触发运行
        run_id = await self.run_workflow(wf_id, inputs, user_id)
        
        # 2. 委托 Manager 监听
        async for event in self.manager.listen(run_id, after_seq_id):
            yield event

    async def resume_stream_generator(
        self, 
        run_id: str, 
        inputs: Dict[str, Any], 
        user_id: str
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 恢复挂起任务并监听流"""
        # 1. 检查是否存在 & 鉴权
        exec_record = await self.exec_repo.get(run_id)
        if not exec_record: 
            raise ValueError(f"Execution {run_id} not found")
        
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError("Permission denied")

        # 2. 准备数据
        wf_id = exec_record["workflow_id"]
        graph = await self._load_graph(wf_id)
        
        # 3. 委托 Manager 恢复运行 (is_resume=True)
        await self.manager.start_execution(run_id, graph, inputs, user_id, is_resume=True)

        # 4. 监听
        async for event in self.manager.listen(run_id, after_seq_id=-1):
            yield event

    async def listen_only(
        self, 
        run_id: str, 
        user_id: str, 
        after_seq_id: int = -1
    ) -> AsyncGenerator[Dict, None]:
        """[SSE] 纯监听 (不触发运行)"""
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError("Permission denied")
            
        async for event in self.manager.listen(run_id, after_seq_id):
            yield event

    # ==========================================
    # 2. 任务管理 (Stop / List)
    # ==========================================

    async def terminate_execution(self, run_id: str, user_id: str):
        """[Action] 终止任务"""
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError("Permission denied")
            
        # 委托 Manager 动手
        await self.manager.terminate_execution(run_id)

    async def list_active_executions(self, user_id: str) -> List[Dict]:
        """查看当前内存中正在跑的任务 (Admin或Debug用)"""
        # 这里演示简单逻辑，实际可能需要过滤 user_id
        # Service 层负责把 run_id 转换成更详细的信息
        return [{"run_id": rid, "status": "running"} for rid in self.manager._active_tasks.keys()]

    async def list_history(self, wf_id: str, user_id: str, page: int, size: int):
        """查看历史记录"""
        # 鉴权
        if not await self.auth_repo.check_ownership(user_id, wf_id):
             pass # 或者抛错，或者只查该用户的
             
        offset = (page - 1) * size
        return await self.exec_repo.list(wf_id, size, offset)

    async def get_details(self, run_id: str, user_id: str):
        if not await self.auth_repo.check_ownership(user_id, run_id):
            raise ValueError("Permission denied")
        return await self.exec_repo.get(run_id)

    # ==========================================
    # 3. 内部辅助 (Helpers)
    # ==========================================

    async def _prepare_new_run(self, wf_id: str, inputs: Dict, user_id: str) -> str:
        """数据库准备工作"""
        if not await self.auth_repo.check_ownership(user_id, wf_id):
            raise ValueError("Permission denied (Workflow access)")
        
        run_id = f"run_{uuid.uuid4().hex}"
        
        # 创建 Session
        await self.session_repo.create_session(
            session_id=run_id, 
            name=f"Run {run_id[:8]}", 
            metadata={"user_id": user_id, "workflow_id": wf_id}
        )
        
        # 创建 Execution Record
        await self.exec_repo.create(run_id, wf_id, inputs)
        
        # 绑定资源权限
        await self.auth_repo.bind(user_id, run_id, "execution")
        
        return run_id

    async def _load_graph(self, wf_id: str):
        """图构建逻辑"""
        wf_def = await self.wf_repo.get(wf_id)
        if not wf_def: 
            raise ValueError("Workflow not found")
        return self.converter.convert(wf_def)