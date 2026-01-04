import asyncio
import uuid
import logging
from typing import Dict, Any, AsyncGenerator,List

# Core Modules
import goose.globals as G
from goose.workflow.scheduler import WorkflowScheduler
from goose.workflow.converter import WorkflowConverter
from goose.adapter import AdapterManager
from goose.workflow import WorkflowDefinition, WorkflowRepository
from goose.app.user.repository import UserResourceRepository

logger = logging.getLogger("goose.app.workflow")

class WorkflowService:
    def __init__(self, 
                 workflow_repository: WorkflowRepository, 
                 workflow_converter: WorkflowConverter, 
                 user_resource_repository: UserResourceRepository):
        self.repo = workflow_repository
        self.converter = workflow_converter
        self.auth_repo = user_resource_repository # 引入关联 Repo

    async def save_workflow(self, workflow: WorkflowDefinition, title: str, user_id: str) -> str:
        if not workflow.id:
            workflow.id = f"wf_{uuid.uuid4().hex[:8]}"
        wid = await self.repo.save(workflow, title)
        await self.auth_repo.bind(user_id, wid, "workflow")
        return wid
    
    async def bind_workflow(self, user_id: str, wid: str):
        await self.auth_repo.bind(user_id, wid, "workflow")

    async def get_workflow(self, wf_id: str) -> WorkflowDefinition:
        return await self.repo.get(wf_id)

    async def list_workflows(self, page: int = 1, size: int = 20) -> List[Dict[str, Any]]:
        offset = (page - 1) * size
        return await self.repo.list(limit=size, offset=offset)
    
    async def list_user_workflows(self, user_id: str, page: int, size: int):
        """
        [查询逻辑变更]
        不能直接查 workflows 表了，需要先查 ID，再查详情
        """
        offset = (page - 1) * size
        
        # 1. 先拿 ID
        wids = await self.auth_repo.get_resource_ids(user_id, "workflow", limit=size, offset=offset)
        
        if not wids:
            return []
        
        workflows = await self.repo.get_batch(wids)
        return workflows
    
    async def import_workflow_from_data(self, data: Dict[str, Any], format: str, user_id: str) -> str:
        """
        导入外部格式 (如 VueFlow JSON) -> 转换为 WorkflowDefinition -> 保存
        """
        # 1. 获取适配器
        adapter = AdapterManager.get_adapter(format) # e.g., 'vueflow'
        if not adapter:
            raise ValueError(f"Unsupported format: {format}")
        
        # 2. 转换数据结构 (Dict -> WorkflowDefinition)
        # 假设 adapter.transform_workflow 返回 WorkflowDefinition 对象
        workflow_def = adapter.transform_workflow(data)
        
        # 3. 保存
        # 如果导入的数据没有 ID，生成一个
        if not workflow_def.id:
            workflow_def.id = f"wf_{uuid.uuid4().hex[:8]}"
            
        return await self.save_workflow(workflow_def, title=data.get("title", "Imported Workflow"), user_id=user_id)

