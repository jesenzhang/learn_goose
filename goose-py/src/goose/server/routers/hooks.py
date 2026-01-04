from fastapi import APIRouter, HTTPException, Request, Depends
from opencoze.app.services.trigger import TriggerManager
from opencoze.server.dependencies import get_trigger_manager
from opencoze.core.protocol.trigger import TriggerType

router = APIRouter(prefix="/api/v1/hooks", tags=["hooks"])

@router.post("/{trigger_id}")
async def webhook_endpoint(
    trigger_id: str, 
    request: Request,
    manager: TriggerManager = Depends(get_trigger_manager)
):
    """
    Webhook 触发入口
    URL: POST /api/v1/hooks/{trigger_id}
    """
    # 1. 查找触发器配置
    trigger = manager.get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(404, "Trigger not found or disabled")

    if trigger.type != TriggerType.WEBHOOK:
        raise HTTPException(400, "Trigger is not a webhook")

    # 2. 转交 Handler 处理
    handler = manager.get_webhook_handler()
    try:
        await handler.handle_request(trigger, request)
    except ValueError as e:
        raise HTTPException(401, str(e)) # Auth failed
    except Exception as e:
        raise HTTPException(500, str(e))
        
    return {"status": "ok", "msg": "Triggered"}