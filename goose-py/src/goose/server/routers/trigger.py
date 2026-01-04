from fastapi import APIRouter, Request, HTTPException, Depends
from goose.server.deps import get_trigger_manager # 需要在 deps 里实现单例获取

router = APIRouter(prefix="/api/v1/triggers", tags=["triggers"])

from goose.server.deps import get_trigger_manager

@router.post("/webhook/{trigger_id}")
async def trigger_webhook(
    trigger_id: str,
    request: Request,
    manager = Depends(get_trigger_manager)
):
    """
    外部系统调用此接口触发工作流
    """
    try:
        await manager.handle_webhook(trigger_id, request)
        return {"status": "ok", "msg": "Triggered"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))