"""
OAuth Authentication

OAuth 认证支持，包括：
- Device Code Flow (设备代码流)
- Token 管理 (存储、刷新)
- Provider-specific OAuth (OpenRouter, Tetrate)

Reference: goose-rs/crates/goose/src/config/signup_openrouter/
Reference: goose-rs/crates/goose/src/config/signup_tetrate/
"""

import os
import json
import asyncio
import time
import threading
import logging
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Protocol
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod
import secrets

logger = logging.getLogger("goose.config.oauth")


class OAuthProvider(str, Enum):
    """OAuth 提供商"""
    OPENROUTER = "openrouter"
    TETRATE = "tetrate"
    CUSTOM = "custom"


@dataclass
class OAuthToken:
    """OAuth Token"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[float] = None
    scope: Optional[str] = None
    
    def is_expired(self) -> bool:
        """检查 Token 是否过期"""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at
    
    def needs_refresh(self) -> bool:
        """检查是否需要刷新 Token"""
        if self.expires_at is None:
            return False
        # 在过期前 5 分钟刷新
        return time.time() >= (self.expires_at - 300)


@dataclass
class DeviceCodeResponse:
    """Device Code 响应"""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    
    def is_expired(self) -> bool:
        """检查 Device Code 是否过期"""
        return time.time() >= (self._created_at + self.expires_in)
    
    _created_at: float = field(default_factory=time.time)


@dataclass
class OAuthConfig:
    """OAuth 配置"""
    provider: OAuthProvider
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    client_secret: Optional[str] = None
    scope: Optional[str] = None
    redirect_uri: Optional[str] = None


class OAuthError(Exception):
    """OAuth 错误"""
    
    def __init__(self, message: str, code: str = "OAUTH_ERROR", details: Optional[Dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class OAuthClient(ABC):
    """OAuth 客户端基类"""
    
    @abstractmethod
    async def get_authorization_url(self) -> str:
        """获取授权 URL"""
        pass
    
    @abstractmethod
    async def start_device_flow(self) -> DeviceCodeResponse:
        """开始 Device Code Flow"""
        pass
    
    @abstractmethod
    async def poll_for_token(self, device_code: str) -> OAuthToken:
        """轮询获取 Token"""
        pass
    
    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> OAuthToken:
        """刷新 Token"""
        pass
    
    @abstractmethod
    async def revoke_token(self, token: str) -> bool:
        """撤销 Token"""
        pass


class DeviceCodeClient(OAuthClient):
    """Device Code Flow OAuth 客户端"""
    
    def __init__(self, config: OAuthConfig, http_client=None):
        self.config = config
        self._http_client = http_client
        self._token_store: Dict[str, OAuthToken] = {}
        self._lock = threading.Lock()
    
    async def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Dict:
        """发送 HTTP 请求"""
        import httpx
        
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        
        try:
            if method.upper() == "POST":
                response = await self._http_client.post(url, data=data, headers=headers)
            else:
                response = await self._http_client.get(url, headers=headers)
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
            except:
                error_data = {}
            raise OAuthError(
                f"OAuth request failed: {e}",
                code=error_data.get("error", "REQUEST_FAILED"),
                details=error_data
            )
    
    async def get_authorization_url(self) -> str:
        """生成授权 URL"""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri or "urn:ietf:wg:oauth:2.0:oob",
            "response_type": "code",
            "scope": self.config.scope or "",
        }
        
        query = "&".join(f"{k}={v}" for k, v in params.items() if v)
        return f"{self.config.authorization_endpoint}?{query}"
    
    async def start_device_flow(self) -> DeviceCodeResponse:
        """开始 Device Code Flow"""
        data = {
            "client_id": self.config.client_id,
            "scope": self.config.scope or "openid profile email",
        }
        
        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret
        
        response = await self._make_request(
            "POST",
            self.config.authorization_endpoint.replace("/authorize", "/device/code"),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        return DeviceCodeResponse(
            device_code=response["device_code"],
            user_code=response["user_code"],
            verification_uri=response["verification_uri"],
            expires_in=response["expires_in"],
            interval=response.get("interval", 5)
        )
    
    async def poll_for_token(self, device_code: str) -> OAuthToken:
        """轮询获取 Token"""
        data = {
            "client_id": self.config.client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        
        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret
        
        while True:
            await asyncio.sleep(5)
            
            response = await self._make_request(
                "POST",
                self.config.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if "access_token" in response:
                return OAuthToken(
                    access_token=response["access_token"],
                    refresh_token=response.get("refresh_token"),
                    token_type=response.get("token_type", "Bearer"),
                    expires_at=time.time() + response.get("expires_in", 3600) if "expires_in" in response else None,
                    scope=response.get("scope")
                )
            
            if response.get("error") == "authorization_pending":
                continue
            elif response.get("error") == "slow_down":
                await asyncio.sleep(5)
                continue
            elif response.get("error") == "expired_token":
                raise OAuthError("Device code expired", code="EXPIRED_TOKEN")
            else:
                raise OAuthError(
                    f"Token poll failed: {response.get('error')}",
                    code=response.get("error", "UNKNOWN")
                )
    
    async def refresh_token(self, refresh_token: str) -> OAuthToken:
        """刷新 Token"""
        data = {
            "client_id": self.config.client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        
        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret
        
        response = await self._make_request(
            "POST",
            self.config.token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        return OAuthToken(
            access_token=response["access_token"],
            refresh_token=response.get("refresh_token", refresh_token),
            token_type=response.get("token_type", "Bearer"),
            expires_at=time.time() + response.get("expires_in", 3600) if "expires_in" in response else None,
            scope=response.get("scope")
        )
    
    async def revoke_token(self, token: str) -> bool:
        """撤销 Token"""
        try:
            await self._make_request(
                "POST",
                self.config.token_endpoint.replace("/token", "/revoke"),
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to revoke token: {e}")
            return False
    
    def store_token(self, key: str, token: OAuthToken) -> None:
        """存储 Token"""
        with self._lock:
            self._token_store[key] = token
    
    def get_token(self, key: str) -> Optional[OAuthToken]:
        """获取 Token"""
        with self._lock:
            return self._token_store.get(key)
    
    def remove_token(self, key: str) -> bool:
        """删除 Token"""
        with self._lock:
            if key in self._token_store:
                del self._token_store[key]
                return True
            return False


class OpenRouterOAuth:
    """OpenRouter OAuth"""
    
    PROVIDER = OAuthProvider.OPENROUTER
    CLIENT_ID = "openrouter"
    AUTHORIZATION_ENDPOINT = "https://openrouter.ai/auth/authorize"
    TOKEN_ENDPOINT = "https://openrouter.ai/auth/token"
    
    def __init__(self):
        self._config = OAuthConfig(
            provider=self.PROVIDER,
            client_id=self.CLIENT_ID,
            authorization_endpoint=self.AUTHORIZATION_ENDPOINT,
            token_endpoint=self.TOKEN_ENDPOINT,
            scope="openid profile email"
        )
        self._client = DeviceCodeClient(self._config)
    
    async def authenticate(self) -> OAuthToken:
        """开始 OAuth 认证流程"""
        # 1. 获取 Device Code
        device_code = await self._client.start_device_flow()
        
        # 2. 显示用户代码和 URL
        print(f"\n请访问: {device_code.verification_uri}")
        print(f"输入代码: {device_code.user_code}")
        print("\n等待认证完成...")
        
        # 3. 轮询获取 Token
        token = await self._client.poll_for_token(device_code.device_code)
        
        print("认证成功!")
        return token
    
    async def refresh(self, refresh_token: str) -> OAuthToken:
        """刷新 Token"""
        return await self._client.refresh_token(refresh_token)
    
    async def revoke(self, token: str) -> bool:
        """撤销 Token"""
        return await self._client.revoke_token(token)
    
    async def get_authorization_url(self) -> str:
        """获取授权 URL (用于代码交换流程)"""
        return await self._client.get_authorization_url()


class TetrateOAuth:
    """Tetrate Agent Router Service OAuth"""
    
    PROVIDER = OAuthProvider.TETRATE
    CLIENT_ID = "goose"
    AUTHORIZATION_ENDPOINT = "https://auth.tetrate.io/authorize"
    TOKEN_ENDPOINT = "https://auth.tetrate.io/oauth/token"
    
    def __init__(self, tenant_id: Optional[str] = None):
        self._tenant_id = tenant_id or os.environ.get("TETRATE_TENANT_ID")
        self._config = OAuthConfig(
            provider=self.PROVIDER,
            client_id=self.CLIENT_ID,
            authorization_endpoint=self.AUTHORIZATION_ENDPOINT,
            token_endpoint=self.TOKEN_ENDPOINT,
            scope="openid profile email offline_access"
        )
        self._client = DeviceCodeClient(self._config)
    
    async def authenticate(self) -> OAuthToken:
        """开始 OAuth 认证流程"""
        # 1. 获取 Device Code
        device_code = await self._client.start_device_flow()
        
        # 2. 显示用户代码和 URL
        print(f"\n请访问: {device_code.verification_uri}")
        print(f"输入代码: {device_code.user_code}")
        print("\n等待认证完成...")
        
        # 3. 轮询获取 Token
        token = await self._client.poll_for_token(device_code.device_code)
        
        print("认证成功!")
        return token
    
    async def refresh(self, refresh_token: str) -> OAuthToken:
        """刷新 Token"""
        return await self._client.refresh_token(refresh_token)
    
    async def revoke(self, token: str) -> bool:
        """撤销 Token"""
        return await self._client.revoke_token(token)
    
    async def get_authorization_url(self) -> str:
        """获取授权 URL"""
        return await self._client.get_authorization_url()


class OAuthManager:
    """OAuth 管理器"""
    
    TOKEN_FILE = "oauth_tokens.json"
    
    _instance: Optional['OAuthManager'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'OAuthManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = OAuthManager()
        return cls._instance
    
    @classmethod
    def set_instance(cls, instance: 'OAuthManager'):
        with cls._lock:
            cls._instance = instance
    
    def __init__(self, config_dir: Optional[str] = None):
        self._config_dir = config_dir or os.path.expanduser("~/.config/goose")
        self._token_file = Path(self._config_dir) / self.TOKEN_FILE
        self._tokens: Dict[str, OAuthToken] = {}
        self._providers: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._load_tokens()
        self._register_default_providers()
    
    def _load_tokens(self) -> None:
        """加载存储的 Token"""
        if self._token_file.exists():
            try:
                with open(self._token_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for provider, token_data in data.items():
                        self._tokens[provider] = OAuthToken(
                            access_token=token_data["access_token"],
                            refresh_token=token_data.get("refresh_token"),
                            token_type=token_data.get("token_type", "Bearer"),
                            expires_at=token_data.get("expires_at"),
                            scope=token_data.get("scope")
                        )
            except Exception as e:
                logger.error(f"Failed to load OAuth tokens: {e}")
    
    def _save_tokens(self) -> None:
        """保存 Token"""
        try:
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for provider, token in self._tokens.items():
                data[provider] = {
                    "access_token": token.access_token,
                    "refresh_token": token.refresh_token,
                    "token_type": token.token_type,
                    "expires_at": token.expires_at,
                    "scope": token.scope
                }
            
            with open(self._token_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved OAuth tokens to {self._token_file}")
        except Exception as e:
            logger.error(f"Failed to save OAuth tokens: {e}")
    
    def _register_default_providers(self) -> None:
        """注册默认 Provider"""
        self._providers[OAuthProvider.OPENROUTER.value] = OpenRouterOAuth()
        self._providers[OAuthProvider.TETRATE.value] = TetrateOAuth()
    
    def register_provider(self, name: str, client: Any) -> None:
        """注册自定义 Provider"""
        with self._lock:
            self._providers[name] = client
    
    async def authenticate(self, provider: str) -> OAuthToken:
        """开始认证流程"""
        if provider not in self._providers:
            raise OAuthError(f"Unknown provider: {provider}", code="UNKNOWN_PROVIDER")
        
        client = self._providers[provider]
        token = await client.authenticate()
        
        # 存储 Token
        with self._lock:
            self._tokens[provider] = token
        self._save_tokens()
        
        return token
    
    async def refresh(self, provider: str) -> OAuthToken:
        """刷新 Token"""
        if provider not in self._providers:
            raise OAuthError(f"Unknown provider: {provider}", code="UNKNOWN_PROVIDER")
        
        token = self._tokens.get(provider)
        if not token or not token.refresh_token:
            raise OAuthError(f"No refresh token for provider: {provider}", code="NO_REFRESH_TOKEN")
        
        client = self._providers[provider]
        new_token = await client.refresh(token.refresh_token)
        
        # 存储新 Token
        with self._lock:
            self._tokens[provider] = new_token
        self._save_tokens()
        
        return new_token
    
    def get_token(self, provider: str) -> Optional[OAuthToken]:
        """获取 Token"""
        return self._tokens.get(provider)
    
    def is_authenticated(self, provider: str) -> bool:
        """检查是否已认证"""
        token = self.get_token(provider)
        return token is not None and not token.is_expired()
    
    def get_authenticated_providers(self) -> List[str]:
        """获取已认证的 Provider"""
        return [p for p in self._tokens.keys() if self.is_authenticated(p)]
    
    async def logout(self, provider: str) -> bool:
        """登出"""
        token = self._tokens.get(provider)
        if token:
            client = self._providers.get(provider)
            if client:
                await client.revoke(token.access_token)
            
            with self._lock:
                del self._tokens[provider]
            self._save_tokens()
            return True
        return False


# 快捷函数

def get_oauth_manager() -> OAuthManager:
    """获取 OAuth 管理器"""
    return OAuthManager.get_instance()


async def authenticate_with_openrouter() -> OAuthToken:
    """使用 OpenRouter 认证"""
    return await get_oauth_manager().authenticate(OAuthProvider.OPENROUTER.value)


async def authenticate_with_tetrate(tenant_id: Optional[str] = None) -> OAuthToken:
    """使用 Tetrate 认证"""
    manager = get_oauth_manager()
    if tenant_id:
        manager._providers[OAuthProvider.TETRATE.value] = TetrateOAuth(tenant_id)
    return await manager.authenticate(OAuthProvider.TETRATE.value)


def get_oauth_token(provider: str) -> Optional[OAuthToken]:
    """获取 OAuth Token"""
    return get_oauth_manager().get_token(provider)


def is_oauth_authenticated(provider: str) -> bool:
    """检查是否已认证"""
    return get_oauth_manager().is_authenticated(provider)


async def refresh_oauth_token(provider: str) -> OAuthToken:
    """刷新 OAuth Token"""
    return await get_oauth_manager().refresh(provider)


async def logout_oauth(provider: str) -> bool:
    """OAuth 登出"""
    return await get_oauth_manager().logout(provider)
