# assistant/api/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from ..utils.ctx_vars import set_auth_token, reset_auth_token

class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token_ctx = None
        
        # 1. 尝试从标准 Header 获取 Token
        auth_header = request.headers.get("Authorization")
        token_str = None
        
        if auth_header and auth_header.startswith("Bearer "):
            token_str = auth_header.replace("Bearer ", "")
        
        # 2. (可选兼容) 如果 Header 没有，尝试从 Query 参数获取 (方便浏览器调试)
        if not token_str:
            token_str = request.query_params.get("token")

        # 3. 注入上下文
        if token_str:
            token_ctx = set_auth_token(token_str)
            
        try:
            # 4. 放行请求，进入具体的 API 路由
            response = await call_next(request)
            return response
        finally:
            # 5. 清理上下文 (非常重要，防止内存泄漏或污染)
            if token_ctx:
                reset_auth_token(token_ctx)