# src/goose/server/utils.py
import json
import asyncio
from typing import AsyncGenerator, Any,Dict,Optional
from fastapi import Request
from goose.events import SystemEvents, Event
from goose.utils.security import create_access_token,decode_access_token
from goose.config import SystemConfig


def create_access_token_by_config(data: Dict, config: SystemConfig) -> str:
    """生成 JWT Token"""
    encoded_jwt = create_access_token(data, config.jwt_secret_key, config.jwt_algorithm, config.jwt_expire_minutes)
    return encoded_jwt

def decode_access_token_by_config(token: str, config: SystemConfig) -> Optional[str]:
    """
    解析 Token 并返回 user_id (sub)
    如果无效或过期，返回 None
    """
    user_id = decode_access_token(token, config.jwt_secret_key, config.jwt_algorithm)
    return user_id

async def sse_wrapper(
    request: Request, 
    generator: AsyncGenerator[Any, None],
    timeout: float = 15.0
) -> AsyncGenerator[str, None]:
    """
    [Shared Utility] Server-Sent Events (SSE) 增强包装器
    
    职责：
    1. 协议转换：Object -> "data: {...}\n\n"
    2. 连接保活：发送 ": keep-alive" 心跳
    3. 异常处理：捕获生成器错误并发送给前端
    4. 优雅断开：监听 request.is_disconnected()
    """
    try:
        # 获取生成器的迭代器
        iterator = generator.__aiter__()
        
        while True:
            # 1. 检查客户端连接状态
            if await request.is_disconnected():
                break

            try:
                # 2. 等待下一个事件 (带超时控制)
                # 如果 Service 层卡死 (如 LLM 响应过慢且无心跳)，这里会触发 Timeout
                event = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
                
                # 3. 序列化数据
                if hasattr(event, "model_dump_json"):
                    # Pydantic V2 对象
                    payload = event.model_dump_json()
                elif isinstance(event, dict):
                    # 字典
                    payload = json.dumps(event, ensure_ascii=False)
                else:
                    # 其他 (如字符串)
                    payload = str(event)
                
                # 4. 发送数据帧
                yield f"data: {payload}\n\n"

                # 5. 检查业务结束信号 (针对 SystemEvent)
                # 如果是 Chat 场景，Service 可能会 yield 特殊的结束包，这里做通用判断
                if isinstance(event, SystemEvents):
                     if event.type in [SystemEvents.WORKFLOW_COMPLETED, SystemEvents.WORKFLOW_FAILED]:
                         yield "data: [DONE]\n\n"
                         break
                     elif event.type == SystemEvents.WORKFLOW_SUSPENDED:
                         yield "data: [SUSPENDED]\n\n"
                         break

            except StopAsyncIteration:
                # 生成器自然结束
                yield "data: [DONE]\n\n"
                break
            
            except asyncio.TimeoutError:
                # 6. 发送心跳包 (注释帧)
                # 浏览器 EventSource 会忽略以冒号开头的行，但这能保持 TCP 连接活跃
                yield ": keep-alive\n\n"
            
            except Exception as e:
                # 7. 捕获序列化或其他运行时错误
                err_payload = json.dumps({
                    "error": str(e), 
                    "type": "INTERNAL_ERROR"
                })
                yield f"data: {err_payload}\n\n"
                break

    except Exception:
        # 兜底：防止在 yield 过程中发生严重错误导致 Server 崩溃
        pass