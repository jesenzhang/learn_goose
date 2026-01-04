from fastapi import APIRouter, Depends, HTTPException,Request
from fastapi.responses import StreamingResponse
from opencoze.server.dto import ChatReq
from opencoze.server.utils.sse import sse_wrapper
from opencoze.server.dependencies import get_chat_service
from opencoze.app.services.chat import ChatService

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post("/completions")
async def chat(req: ChatReq, 
               request: Request, # [必须] 需要 Request 对象来检测断开
               service: ChatService = Depends(get_chat_service)):
   # ChatService.chat_stream 返回的是 AsyncGenerator
    generator = service.chat_stream(req.conversation_id, req.query, "user_id")
    
    return StreamingResponse(
        sse_wrapper(request, generator),
        media_type="text/event-stream"
    )
    
@router.post("/conversations")
async def create_conversation(
    payload: dict, # {"app_id": "..."}
    service: ChatService = Depends(get_chat_service)
):
    cid = await service.create_conversation(payload["app_id"], "user_default")
    return {"id": cid}