from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any
# Schemas
from goose.server.schemas import ApiResponse, WorkflowReq, RunReq, PaginatedResponse
# Services (from App layer)
from goose.app.workflow.service import WorkflowService
from goose.app.execution.service import ExecutionService
# Deps
from goose.server.utils import sse_wrapper

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])

from goose.server.deps import get_wf_service, get_exec_service,get_current_user_id

# --- Workflow CRUD ---

@router.post("/save")
async def save_workflow(
    req: WorkflowReq, 
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    try:
        wid = await service.save_workflow(req.workflow, req.title)
        return ApiResponse(data={"id": wid})
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/{wf_id}")
async def get_workflow(
    wf_id: str, 
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    wf = await service.get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return ApiResponse(data=wf)

@router.get("/")
async def list_workflows(
    page: int = 1, 
    size: int = 20, 
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    items = await service.list_workflows(page, size)
    return PaginatedResponse(data=items, pagination={"page": page, "page_size": size, "total": 0}) # total需额外查

# --- Execution ---

@router.post("/{wf_id}/run")
async def run_workflow(
    wf_id: str,
    req: RunReq,
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    try:
        eid = await service.run_workflow(wf_id, req.inputs)
        return ApiResponse(data={"execution_id": eid, "status": "pending"})
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{wf_id}/stream")
async def stream_workflow(
    wf_id: str,
    req: RunReq,
    request: Request,
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    try:
        generator = service.execute_stream_generator(wf_id, req.inputs)
        return StreamingResponse(
            sse_wrapper(request, generator),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/{wf_id}/executions")
async def list_executions(
    wf_id: str,
    page: int = 1,
    size: int = 20,
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    items = await service.list_executions(wf_id, page, size)
    return PaginatedResponse(data=items)


@router.post("/import")
async def import_workflow(
    data: Dict[str, Any],
    format: str = "vueflow",
    service: WorkflowService = Depends(get_wf_service),
    user_id: str = Depends(get_current_user_id)
):
    try:
        # Adapter 解析 (CPU)
        wid =await service.import_workflow_from_data(data, format=format,user_id=user_id)
        if not wid:
            raise ValueError("Empty workflow")
        
        return ApiResponse(data={"id": wid})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))