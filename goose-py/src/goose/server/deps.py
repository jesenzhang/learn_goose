from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from typing import TYPE_CHECKING
from goose.app.user.service import UserService
from goose.config import SystemConfig
from goose.server.utils import decode_access_token_by_config

from goose.app.trigger.manager import TriggerManager
from goose.app.execution.service import ExecutionService
from goose.app.workflow.service import WorkflowService

   
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def _get_state_attr(request: Request, attr: str):
    val = getattr(request.app.state, attr, None)
    if not val:
        raise HTTPException(500, f"System service '{attr}' not initialized")
    return val

def get_wf_service(request: Request) -> WorkflowService:
    """获取 WorkflowService 实例"""
    return _get_state_attr(request, "workflow_service")

def get_exec_service(request: Request) -> ExecutionService:
    """获取 ExecutionService 实例"""
    return _get_state_attr(request, "execution_service")

def get_user_service(request: Request) -> UserService:
    """获取 UserService 实例"""
    return _get_state_attr(request, "user_service")

def get_sys_config(request: Request):
    """获取系统配置"""
    return _get_state_attr(request, "sys_config")

# --- Managers (Stateful Singleton) ---
# TriggerManager 必须是单例，因为它内部维护了 APScheduler 的句柄

def get_trigger_manager(request: Request) -> "TriggerManager":
    """
    从 App State 中获取 TriggerManager 单例
    注意：这要求 main.py 的 lifespan 中必须执行了 app.state.trigger_manager = ...
    """
    tm = getattr(request.app.state, "trigger_manager", None)
    if not tm:
        raise RuntimeError("TriggerManager is not initialized. Is the app booting correctly?")
    return tm


async def get_current_user_id(
    token: str = Depends(oauth2_scheme),
    service: UserService = Depends(get_user_service),
    sys_config: SystemConfig = Depends(get_sys_config)
) -> str:
    """
    [生产级鉴权]
    1. 从 Authorization: Bearer <token> 解析 Token
    2. 验证签名和有效期
    3. 提取 user_id
    """
    # 1. 解码 Token
    user_id = decode_access_token_by_config(token,sys_config)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. (可选) 验证用户是否还存在/未被封禁
    # 这一步会增加一次数据库查询，视性能要求而定
    # 如果你是纯无状态设计，可以跳过这一步，直接信赖 Token
    
    user = await service.repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found"
        )
        
    return user_id