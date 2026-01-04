# src/goose/server/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from goose.config import SystemConfig
from pydantic import BaseModel

from goose.server.utils import create_access_token_by_config,decode_access_token_by_config
from goose.app.user.service import UserService
from goose.server.deps import get_user_service,get_sys_config

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/token", response_model=Token)
async def login_for_access_token(
    # OAuth2PasswordRequestForm 是 FastAPI 标准表单 (username, password)
    # 在我们的场景下，username 可以是 user_id，password 可以是 api_key
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: UserService = Depends(get_user_service),
    config: SystemConfig = Depends(get_sys_config)
):
    """
    换取 JWT Token
    - username: 输入 user_id (例如 'admin')
    - password: 输入 api_key (例如 'sk-goose-...')
    """
    # 1. 验证凭证
    # 这是一个假设的方法，你需要确保 UserService 有这个逻辑
    # 逻辑：查找 user_id，并比对 api_key 是否匹配
    user = await service.repo.get_by_id(form_data.username)
    
    if not user or user["api_key"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect user_id or api_key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 生成 Token
    access_token = create_access_token_by_config(data={"sub": user["id"]}, config=config)
    
    return {"access_token": access_token, "token_type": "bearer"}