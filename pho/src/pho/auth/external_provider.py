"""
External Auth Provider - 外置认证提供者

通过外部认证服务进行 token 验证和用户信息获取。
"""

import logging
import httpx
from typing import Dict, Any, Optional
from datetime import datetime

from .protocol import AuthProvider, TokenAuth, UserInfo, AuthConfig

logger = logging.getLogger(__name__)


class ExternalAuthProvider:
    """
    外置认证提供者

    通过 HTTP API 连接到外部认证服务。
    """

    def __init__(self, config: AuthConfig):
        """
        初始化外置认证提供者

        Args:
            config: 认证配置，必须包含 external_auth_url
        """
        self.config = config
        self.base_url = config.external_auth_url.rstrip('/') if config.external_auth_url else None
        self.api_key = config.external_auth_api_key
        self.timeout = config.external_auth_timeout
        self.token_header = config.token_header_name
        self.token_prefix = config.token_prefix

        self._session: Optional[httpx.AsyncClient] = None
        self._initialized = False

        if not self.base_url:
            logger.warning("ExternalAuthProvider initialized without external_auth_url")

    async def initialize(self) -> bool:
        """初始化认证提供者"""
        if self._initialized:
            return True

        if not self.base_url:
            logger.warning("Cannot initialize ExternalAuthProvider: no external_auth_url configured")
            return False

        try:
            # 创建 HTTP 客户端
            self._session = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._get_headers()
            )

            # 健康检查
            is_healthy = await self.health_check()
            if not is_healthy:
                logger.warning(f"External auth service health check failed: {self.base_url}")
                # 但仍然继续，可能是暂时性问题

            self._initialized = True
            logger.info(f"ExternalAuthProvider initialized: {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ExternalAuthProvider: {e}", exc_info=e)
            return False

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json"
        }

        if self.api_key:
            headers["X-API-Key"] = self.api_key

        if token:
            headers[self.token_header] = f"{self.token_prefix} {token}"

        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """执行 HTTP 请求"""
        if not self.base_url:
            raise RuntimeError("External auth service not configured")

        if not self._session:
            raise RuntimeError("AuthProvider not initialized")

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = await self._session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=self._get_headers(token)
            )

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request Error: {e}")
            raise

    async def validate_token(self, token: str) -> Optional[UserInfo]:
        """
        验证 token 并返回用户信息

        Args:
            token: 认证 token

        Returns:
            用户信息，如果 token 无效则返回 None
        """
        if not self._initialized:
            logger.warning("AuthProvider not initialized")
            return None

        try:
            result = await self._request(
                method="GET",
                endpoint="/auth/validate",
                token=token
            )

            # 解析响应
            if result.get("code") == 200 or result.get("status") == 1:
                data = result.get("data", {})

                # 解析用户信息
                user_id = data.get("user_id") or data.get("id") or ""
                username = data.get("username") or ""
                display_name = data.get("display_name") or data.get("name") or username
                email = data.get("email")
                permissions = data.get("permissions", {})

                return UserInfo(
                    user_id=user_id,
                    username=username,
                    display_name=display_name,
                    email=email,
                    permissions=permissions,
                    created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
                    last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else datetime.now(),
                    metadata=data.get("metadata")
                )

            # Token 无效
            logger.debug(f"Token validation failed: {token[:10]}...")
            return None
        except Exception as e:
            logger.error(f"Failed to validate token: {e}", exc_info=e)
            return None

    async def close(self) -> None:
        """关闭认证提供者"""
        if self._session:
            await self._session.aclose()
            self._session = None

        self._initialized = False
        logger.info("ExternalAuthProvider closed")

    async def health_check(self) -> bool:
        """健康检查"""
        if not self.base_url:
            return False

        try:
            await self._request("GET", "/health")
            return True
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    async def refresh_token(self, old_token: str) -> Optional[str]:
        """
        刷新 token

        Args:
            old_token: 旧的 token

        Returns:
            新的 token，如果刷新失败则返回 None
        """
        if not self._initialized:
            return None

        try:
            result = await self._request(
                method="POST",
                endpoint="/auth/refresh",
                data={"old_token": old_token},
                token=old_token
            )

            if result.get("code") == 200 or result.get("status") == 1:
                return result.get("data", {}).get("new_token")

            return None
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}", exc_info=e)
            return None

    async def get_user_info(self, token: str) -> Optional[UserInfo]:
        """
        获取当前用户信息

        Args:
            token: 认证 token

        Returns:
            用户信息，如果获取失败则返回 None
        """
        # 复用 validate_token 逻辑，如果 API 有专门端点可覆盖
        return await self.validate_token(token)

    async def invalidate_token(self, token: str) -> bool:
        """
        使 token 失效（注销）

        Args:
            token: 要注销的 token

        Returns:
            是否成功
        """
        if not self._initialized:
            return False

        try:
            result = await self._request(
                method="POST",
                endpoint="/auth/invalidate",
                data={"token": token},
                token=token
            )

            return result.get("code") == 200 or result.get("status") == 1
        except Exception as e:
            logger.error(f"Failed to invalidate token: {e}", exc_info=e)
            return False
