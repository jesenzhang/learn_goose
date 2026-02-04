# assistant/utils/ctx_vars.py
from contextvars import ContextVar, Token as ContextToken
from typing import Optional

# 定义一个全局 ContextVar，但在每个 Request 中是隔离的
_request_auth_token: ContextVar[Optional[str]] = ContextVar("request_auth_token", default=None)
_request_auth_header: ContextVar[Optional[str]] = ContextVar("request_auth_header", default=None)

def get_auth_token() -> Optional[str]:
    return _request_auth_token.get()

def get_auth_header() -> Optional[str]:
    return _request_auth_header.get()

def set_auth_token(token: str) -> ContextToken:
    return _request_auth_token.set(token)

def reset_auth_token(token: ContextToken) -> None:
    _request_auth_token.reset(token)

def set_auth_context(token: Optional[str], header: Optional[str]) -> tuple[ContextToken, ContextToken]:
    token_ctx = _request_auth_token.set(token)
    header_ctx = _request_auth_header.set(header)
    return token_ctx, header_ctx

def reset_auth_context(tokens: tuple[ContextToken, ContextToken]) -> None:
    token_ctx, header_ctx = tokens
    _request_auth_token.reset(token_ctx)
    _request_auth_header.reset(header_ctx)
