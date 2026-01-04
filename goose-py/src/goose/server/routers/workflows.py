from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from goose.server.schemas import ApiResponse, WorkflowReq, PaginatedResponse
from goose.app.workflow.service import WorkflowService
from goose.server.deps import get_wf_service, get_current_user_id

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])

# --- Workflow Definition CRUD Only ---

@router.post("/save")
async def save_workflow(
    req: WorkflowReq, 
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    wid = await service.save_workflow(req.workflow, req.title, user_id)
    return ApiResponse(data={"id": wid})

@router.get("/{wf_id}")
async def get_workflow(
    wf_id: str, 
    service: WorkflowService = Depends(get_wf_service)
):
    wf = await service.get_workflow(wf_id)
    if not wf: raise HTTPException(404, "Workflow not found")
    return ApiResponse(data=wf)

@router.get("/")
async def list_workflows(
    page: int = 1, 
    size: int = 20, 
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    # 这里应该传入 user_id 进行过滤
    items = await service.list_user_workflows(user_id, page, size)
    return PaginatedResponse(data=items)

@router.post("/import")
async def import_workflow(
    data: Dict[str, Any],
    format: str = 'vueflow',
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    wid = await service.import_workflow_from_data(data,format, user_id=user_id)
    return ApiResponse(data={"id": wid})