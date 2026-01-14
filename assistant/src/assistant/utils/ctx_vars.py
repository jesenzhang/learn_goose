# assistant/utils/ctx_vars.py
from contextvars import ContextVar, Token as ContextToken
from typing import Optional

# 定义一个全局 ContextVar，但在每个 Request 中是隔离的
_request_auth_token: ContextVar[Optional[str]] = ContextVar("request_auth_token", default=None)

def get_auth_token() -> Optional[str]:
    return _request_auth_token.get()

def set_auth_token(token: str) -> ContextToken:
    return _request_auth_token.set(token)

def reset_auth_token(token: ContextToken) -> None:
    _request_auth_token.reset(token)