from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse

from goose.server.schemas import ApiResponse, RunReq, ResumeReq, SingleNodeRunReq, ExecutionDTO
from goose.app.execution.service import ExecutionService
from goose.server.utils import sse_wrapper

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])

from goose.server.deps import get_exec_service,get_current_user_id

# --- 1. 运行与恢复 ---

@router.post("/{wf_id}/run", status_code=status.HTTP_202_ACCEPTED, response_model=ApiResponse)
async def run_workflow(
    wf_id: str,
    req: RunReq,
    svc: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """[Async] 提交新任务"""
    try:
        eid = await svc.run_workflow(wf_id, req.inputs,target_node_id=req.target_node_id,user_id=user_id)
        return ApiResponse(data={"execution_id": eid, "status": "pending"})
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{eid}/resume", response_model=ApiResponse)
async def resume_execution(
    eid: str,
    req: ResumeReq,
    svc: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """[Async] 恢复暂停/失败的任务"""
    try:
        await svc.resume_workflow(eid, req.inputs)
        return ApiResponse(data={"execution_id": eid, "status": "resuming"})
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

# --- 2. 状态查询 ---

@router.get("/{eid}", response_model=ApiResponse[ExecutionDTO])
async def get_execution(
    eid: str,
    svc: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """获取执行详情"""
    try:
        data = await svc.get_execution_detail(eid)
        return ApiResponse(data=data)
    except ValueError:
        raise HTTPException(404, "Execution not found")

# --- 3. 测试与调试 ---

@router.post("/node/test", response_model=ApiResponse)
async def test_single_node(
    req: SingleNodeRunReq,
    svc: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """[Sync] 独立测试运行单个节点"""
    try:
        output = await svc.test_single_node(req.node_type, req.config, req.inputs, req.mock_context)
        return ApiResponse(data={"output": output})
    except Exception as e:
        raise HTTPException(500, str(e))

# --- 4. 流式接口 ---

@router.post("/{workflow_id}/stream")
async def stream_new_run(
    workflow_id: str,
    req: RunReq,
    request: Request,
    svc: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """[Chat Mode] 启动新任务并立即流式返回"""
    try:
        # 1. 启动任务
        run_id = await svc.run_workflow(workflow_id, req.inputs)
        
        # 2. 获取生成器 (from start)
        generator = svc.get_event_generator(run_id)
        
        return StreamingResponse(
            sse_wrapper(request, generator),
            media_type="text/event-stream",
            headers={"X-Execution-ID": run_id} # 方便前端拿到 ID
        )
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/{eid}/stream")
async def stream_existing_run(
    eid: str,
    request: Request,
    last_event_id: int = Query(-1, alias="Last-Event-ID"),
    svc: ExecutionService = Depends(get_exec_service),
    user_id: str = Depends(get_current_user_id)
):
    """
    [Observer Mode] 监听已存在的任务
    支持通过 Last-Event-ID 进行断点回填
    """
    try:
        generator = svc.get_event_generator(eid, last_event_id)
        return StreamingResponse(
            sse_wrapper(request, generator),
            media_type="text/event-stream"
        )
    except ValueError:
        raise HTTPException(404, "Execution not found")