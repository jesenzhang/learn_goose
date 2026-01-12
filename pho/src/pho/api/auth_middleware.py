"""
API 认证中间件

提供 FastAPI 认证和授权中间件
"""

import logging
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from ..auth import (
    get_auth_service,
    get_authz_service,
    AuthUser,
    Permission,
)

logger = logging.getLogger(__name__)

# 安全认证方案
security = HTTPBearer(auto_error=False)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    认证中间件

    验证请求中的认证令牌，并将用户信息附加到请求状态中
    """

    # 不需要认证的路径
    EXEMPT_PATHS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
        "/auth/login",
        "/auth/register",
    }

    async def dispatch(self, request: Request, call_next):
        """处理请求，添加认证信息"""
        path = request.url.path

        # 检查是否豁免认证
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return await call_next(request)

        # 提取认证令牌
        auth_header = request.headers.get("Authorization")
        token = None

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # 移除 "Bearer " 前缀

        # 验证令牌
        user: Optional[AuthUser] = None
        if token:
            auth_service = get_auth_service()
            user = await auth_service.authenticate_by_token(token)

        # 将用户信息添加到请求状态
        request.state.user = user

        # 继续处理请求
        response = await call_next(request)
        return response


async def get_current_user(request: Request) -> Optional[AuthUser]:
    """
    获取当前认证用户

    Args:
        request: FastAPI 请求对象

    Returns:
        当前用户，未认证返回 None
    """
    return getattr(request.state, "user", None)


async def require authenticated_user(request: Request) -> AuthUser:
    """
    要求用户必须认证

    Args:
        request: FastAPI 请求对象

    Returns:
        当前用户

    Raises:
        HTTPException: 如果用户未认证
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission(required_permission: Permission):
    """
    要求特定权限的依赖项工厂函数

    Args:
        required_permission: 需要的权限级别

    Returns:
        FastAPI 依赖项函数
    """
    async def check_permission(request: Request) -> AuthUser:
        user = await authenticated_user(request)

        authz_service = get_authz_service()
        has_permission = await authz_service.check_permission(
            user.id,
            required_permission
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{required_permission}' required",
            )

        return user

    return check_permission


async def require_session_access(
    request: Request,
    session_id: str
) -> AuthUser:
    """
    要求用户可访问指定会话

    Args:
        request: FastAPI 请求对象
        session_id: 会话 ID

    Returns:
        当前用户

    Raises:
        HTTPException: 如果用户无权访问会话
    """
    user = await authenticated_user(request)

    # 检查会话访问权限
    from ..session import SessionRepository

    session_repo = SessionRepository()
    authz_service = get_authz_service()

    has_access = await authz_service.check_session_access(
        user.id,
        session_id,
        session_repo
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to session '{session_id}'",
        )

    return user


# ================= 路由装饰器 =================

def require_auth(func: Callable):
    """
    路由处理器装饰器：要求用户认证

    使用方式：
        @router.get("/sessions")
        @require_auth
        async def list_sessions(request: Request):
            user = await get_current_user(request)
            ...
    """
    async def wrapper(*args, **kwargs):
        # 查找 request 参数
        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

        if not request:
            raise RuntimeError("@require_auth requires a Request parameter")

        user = await authenticated_user(request)
        # 将用户添加到 kwargs
        kwargs["current_user"] = user

        return await func(*args, **kwargs)

    return wrapper


# ================= FastAPI 依赖项 (使用方式 2) =================

def get_optional_user():
    """
    可选用户依赖项

    不会抛出异常，未认证返回 None

    使用方式：
        @router.get("/public")
        async def public_endpoint(user: Optional[AuthUser] = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello {user.username}"}
            return {"message": "Hello, anonymous user"}
    """
    async def _get_user(request: Request) -> Optional[AuthUser]:
        return await get_current_user(request)

    return _get_user


def get_required_user():
    """
    必须认证的用户依赖项

    未认证抛出 401 异常

    使用方式：
        @router.post("/sessions")
        async def create_session(user: AuthUser = Depends(get_required_user)):
            return {"user_id": user.id}
    """
    return authenticated_user
