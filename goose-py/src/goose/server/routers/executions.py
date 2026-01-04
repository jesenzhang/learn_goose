from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse

from goose.server.schemas import (
    ApiResponse, 
    PaginatedResponse, 
    ExecutionCreateReq, 
    RunReq
)
from goose.server.utils import sse_wrapper
from goose.app.execution.service import ExecutionService
from goose.server.deps import get_exec_service, get_current_user_id

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])

# 1. 异步运行 (返回 ID)
@router.post("/run")
async def run_execution(
    req: ExecutionCreateReq, 
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    try:
        eid = await service.run_workflow(req.workflow_id, req.inputs, user_id)
        return ApiResponse(data={"execution_id": eid, "status": "pending"})
    except Exception as e:
        raise HTTPException(500, str(e))

# 2. 流式运行 (新任务)
@router.post("/stream")
async def stream_execution(
    req: ExecutionCreateReq,
    request: Request,
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    try:
        generator = service.execute_stream_generator(req.workflow_id, req.inputs, user_id)
        return StreamingResponse(
            sse_wrapper(request, generator),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(500, str(e))

# 3. [新增] 恢复挂起任务 (Resume + Stream)
@router.post("/{run_id}/resume")
async def resume_execution(
    run_id: str,
    req: RunReq, # 复用 RunReq，inputs 作为 resume 时的上下文更新
    request: Request,
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """
    恢复执行。通常用于 "Human-in-the-loop" 场景。
    用户提交输入后，SSE 连接保持，直到任务完成或再次挂起。
    """
    try:
        generator = service.resume_stream_generator(run_id, req.inputs, user_id)
        return StreamingResponse(
            sse_wrapper(request, generator),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(500, str(e))

# 4. 查询列表
@router.get("/")
async def list_executions(
    workflow_id: str = Query(..., description="Workflow ID"),
    page: int = 1, 
    size: int = 20, 
    service: ExecutionService = Depends(get_exec_service)
):
    # 这里建议增加 user_id 过滤
    items = await service.list_executions(workflow_id, page, size)
    return PaginatedResponse(data=items)

# 5. 查询详情
@router.get("/{run_id}")
async def get_execution(
    run_id: str,
    service: ExecutionService = Depends(get_exec_service)
):
    item = await service.get_execution(run_id)
    return ApiResponse(data=item)