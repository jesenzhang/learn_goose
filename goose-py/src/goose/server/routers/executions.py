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

@router.get("/active")
async def get_active_executions(
    service: ExecutionService = Depends(get_exec_service),
    # 仅限管理员
    user_id: str = Depends(get_current_user_id) 
):
    return ApiResponse(data=await service.list_active_executions())

@router.post("/{run_id}/stop")
async def stop_execution(
    run_id: str,
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """
    [管理] 强制停止任务
    """
    try:
        await service.terminate_execution(run_id, user_id)
        return ApiResponse(message="Execution terminated")
    except ValueError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    
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

@router.get("/{run_id}/events")
async def listen_execution_events(
    run_id: str,
    after_seq_id: int = Query(-1, description="从哪个序列号开始(-1=从头开始)"),
    request: Request = None, # 用于检测客户端断开
    service: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """
    [SSE] 监听指定任务的事件流
    适用于: 
    1. 异步任务启动后的被动监听
    2. 页面刷新后的断线重连
    """
    try:
        generator = service.listen_to_execution(
            run_id=run_id, 
            user_id=user_id, 
            after_seq_id=after_seq_id
        )
        return StreamingResponse(
            sse_wrapper(request, generator),
            media_type="text/event-stream"
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
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
        generator = service.execute_stream_generator(
            req.workflow_id, 
            req.inputs, 
            user_id,
            after_seq_id=req.after_seq_id 
        )
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