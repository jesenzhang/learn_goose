"""
认证中间件

提供 FastAPI 认证和授权中间件
"""

import logging
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..auth import get_auth_service, AuthUser

logger = logging.getLogger(__name__)

# HTTP Bearer 认证方案
security = HTTPBearer(auto_error=False)


async def extract_from_auth_header(auth_header: Optional[str]) -> Optional[str]:
    """
    从 Authorization 头提取令牌

    Args:
        auth_header: Authorization 头值

    Returns:
        令牌字符串，如果不存在则返回 None
    """
    if not auth_header:
        return None

    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return auth_header


async def get_current_user(request: Request) -> Optional[AuthUser]:
    """
    获取当前认证的用户（可选）

    如果没有提供令牌或令牌无效，返回 None 而不是抛出异常

    Args:
        request: FastAPI 请求对象

    Returns:
        认证用户对象，未认证则返回 None
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        token = await extract_from_auth_header(auth_header)
        if not token:
            return None

        auth_service = get_auth_service()
        user = await auth_service.authenticate_by_token(token)

        return user
    except Exception as e:
        logger.warning(f"Authentication failed: {e}")
        return None


async def get_required_user(request: Request) -> AuthUser:
    """
    获取当前认证的用户（必需）

    如果没有提供令牌或令牌无效，抛出 401 异常

    Args:
        request: FastAPI 请求对象

    Returns:
        认证用户对象

    Raises:
        HTTPException: 如果未认证或认证失败
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = await extract_from_auth_header(auth_header)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()
    user = await auth_service.authenticate_by_token(token)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )

    return user


async def get_admin_user(request: Request) -> AuthUser:
    """
    获取当前认证的管理员用户

    如果用户不是管理员，抛出 403 异常

    Args:
        request: FastAPI 请求对象

    Returns:
        认证的管理员用户对象

    Raises:
        HTTPException: 如果未认证或不是管理员
    """
    user = await get_required_user(request)

    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )

    return user


async def check_user_owns_session(
    session_id: str,
    user: AuthUser = Depends(get_required_user)
) -> bool:
    """
    检查用户是否拥有会话

    Args:
        session_id: 会话 ID
        user: 认证用户

    Returns:
        是否拥有会话

    Raises:
        HTTPException: 如果用户没有权限访问该会话
    """
    from ..db import get_db

    db = get_db()

    # 尝试加载会话状态
    state = await db.load_state_for_user(user.id, session_id)

    if not state:
        # 会话不存在或用户无权访问
        # 管理员可以查看所有会话
        if user.is_admin:
            state = await db.load_state(session_id)
            if state:
                return True

        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found or access denied"
        )

    return True


# FastAPI 依赖函数
async def optional_auth_user(request: Request) -> Optional[AuthUser]:
    """可选认证依赖 - 用于不需要认证的端点"""
    return await get_current_user(request)


async def require_auth_user(request: Request) -> AuthUser:
    """必需认证依赖 - 用于需要认证的端点"""
    return await get_required_user(request)


async def require_admin_user(request: Request) -> AuthUser:
    """管理员认证依赖 - 用于需要管理员权限的端点"""
    return await get_admin_user(request)


# 便捷函数（兼容性）
def get_user(request: Request) -> Optional[AuthUser]:
    """同步包装器（用于向后兼容）"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果在异步上下文中，创建任务
            return asyncio.create_task(get_current_user(request))
        else:
            # 如果不在异步上下文中，运行协程
            return asyncio.run(get_current_user(request))
    except:
        return None
