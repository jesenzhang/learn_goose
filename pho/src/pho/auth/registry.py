"""
Auth Provider Registry - 认证提供者注册中心

管理所有认证提供者，支持动态切换认证模式。
"""

import logging
from typing import Dict, Optional, Any

from .protocol import (
    AuthProvider, AuthConfig, AuthMode,
    TokenAuth, UserAuth,
    UserInfo
)
from .local_provider import LocalAuthProvider
from .external_provider import ExternalAuthProvider

logger = logging.getLogger(__name__)


class AuthProviderRegistry:
    """
    认证提供者注册中心

    支持两种认证模式的动态切换：
    - Local: 使用 LocalAuthProvider
    - External: 使用 ExternalAuthProvider
    """

    def __init__(self, config: AuthConfig, db_manager=None):
        """
        初始化认证提供者注册中心

        Args:
            config: 认证配置
            db_manager: 数据库管理器（仅用于本地模式）
        """
        self.config = config
        self._db_manager = db_manager
        self._provider: Optional[AuthProvider] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        初始化认证系统

        根据配置选择并初始化对应的认证提供者。
        """
        if not self.config.enabled:
            logger.info("Auth is disabled in config")
            return True

        try:
            # 根据模式选择提供者
            if self.config.mode == AuthMode.LOCAL:
                self._provider = LocalAuthProvider(self.config, self._db_manager)
            elif self.config.mode == AuthMode.EXTERNAL:
                self._provider = ExternalAuthProvider(self.config)
            else:
                # 默认使用本地模式
                logger.warning(f"Unknown auth mode: {self.config.mode}, defaulting to LOCAL")
                self._provider = LocalAuthProvider(self.config, self._db_manager)

            # 初始化提供者
            success = await self._provider.initialize()

            if success:
                self._initialized = True
                mode_name = self.config.mode.value.upper()
                logger.info(f"AuthProviderRegistry initialized with {mode_name} mode")
            else:
                logger.error(f"Failed to initialize auth provider")

            return success
        except Exception as e:
            logger.error(f"Failed to initialize AuthProviderRegistry: {e}", exc_info=e)
            return False

    def get_provider(self) -> Optional[AuthProvider]:
        """
        获取当前认证提供者

        Returns:
            当前认证提供者实例
        """
        return self._provider

    def is_local_mode(self) -> bool:
        """检查是否为本地认证模式"""
        return self.config.mode == AuthMode.LOCAL

    def is_external_mode(self) -> bool:
        """检查是否为外置认证模式"""
        return self.config.mode == AuthMode.EXTERNAL

    async def validate_token(self, token: str) -> Optional[UserInfo]:
        """
        验证 token（外置模式）

        Args:
            token: 认证 token

        Returns:
            用户信息，如果 token 无效则返回 None
        """
        if not self._initialized or not self._provider:
            logger.warning("AuthProviderRegistry not initialized")
            return None

        if self.is_external_mode() and isinstance(self._provider, TokenAuth):
            return await self._provider.validate_token(token)

        # 本地模式不支持 token 验证
        logger.debug("Token validation not supported in local mode")
        return None

    async def register_user(
        self,
        username: str,
        password: str,
        **kwargs
    ) -> bool:
        """
        注册用户（本地模式）

        Args:
            username: 用户名
            password: 密码
            **kwargs: 其他参数

        Returns:
            是否注册成功
        """
        if not self._initialized or not self._provider:
            logger.warning("AuthProviderRegistry not initialized")
            return False

        if self.is_local_mode() and isinstance(self._provider, UserAuth):
            return await self._provider.register_user(username, password, **kwargs)

        # 外置模式不支持用户注册
        logger.debug("User registration not supported in external mode")
        return False

    async def authenticate_user(
        self,
        username: str,
        password: str
    ) -> Optional[UserInfo]:
        """
        用户登录认证（本地模式）

        Args:
            username: 用户名
            password: 密码

        Returns:
            用户信息，如果认证失败则返回 None
        """
        if not self._initialized or not self._provider:
            logger.warning("AuthProviderRegistry not initialized")
            return None

        if self.is_local_mode() and isinstance(self._provider, UserAuth):
            return await self._provider.authenticate_user(username, password)

        # 外置模式不支持用户名密码认证
        logger.debug("User authentication not supported in external mode")
        return None

    async def get_user_info(self, user_id: str, token: Optional[str] = None) -> Optional[UserInfo]:
        """
        获取用户信息

        Args:
            user_id: 用户 ID
            token: 认证 token（外置模式）

        Returns:
            用户信息，如果获取失败则返回 None
        """
        if not self._initialized or not self._provider:
            logger.warning("AuthProviderRegistry not initialized")
            return None

        if self.is_external_mode() and token:
            return await self._provider.get_user_info(token)
        elif self.is_local_mode() and isinstance(self._provider, LocalAuthProvider):
            return await self._provider.get_user_info(user_id)

        return None

    async def refresh_token(self, old_token: str) -> Optional[str]:
        """
        刷新 token（外置模式）

        Args:
            old_token: 旧的 token

        Returns:
            新的 token，如果刷新失败则返回 None
        """
        if not self._initialized or not self._provider:
            return None

        if self.is_external_mode() and isinstance(self._provider, ExternalAuthProvider):
            return await self._provider.refresh_token(old_token)

        return None

    async def invalidate_token(self, token: str) -> bool:
        """
        使 token 失效（注销）

        Args:
            token: 要注销的 token

        Returns:
            是否成功
        """
        if not self._initialized or not self._provider:
            return False

        if self.is_external_mode() and isinstance(self._provider, ExternalAuthProvider):
            return await self._provider.invalidate_token(token)

        return False

    async def list_users(self, limit: int = 100, token: Optional[str] = None) -> list[UserInfo]:
        """
        列出用户（本地模式）

        Args:
            limit: 返回数量限制
            token: 认证 token（外置模式，可选）

        Returns:
            用户列表
        """
        if not self._initialized or not self._provider:
            return []

        if self.is_local_mode() and isinstance(self._provider, LocalAuthProvider):
            return await self._provider.list_users(limit)

        return []

    async def delete_user(self, user_id: str, token: Optional[str] = None) -> bool:
        """
        删除用户（本地模式）

        Args:
            user_id: 用户 ID
            token: 认证 token（外置模式，可选）

        Returns:
            是否删除成功
        """
        if not self._initialized or not self._provider:
            return False

        if self.is_local_mode() and isinstance(self._provider, LocalAuthProvider):
            return await self._provider.delete_user(user_id)

        return False

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._initialized or not self._provider:
            return False

        return await self._provider.health_check()

    async def close(self) -> None:
        """关闭认证系统"""
        if self._provider:
            await self._provider.close()
        self._provider = None
        self._initialized = False
        logger.info("AuthProviderRegistry closed")


# ================= Global Instance Management =================

_global_registry: Optional[AuthProviderRegistry] = None


def init_registry(config: AuthConfig, db_manager=None) -> AuthProviderRegistry:
    """
    初始化全局认证注册中心

    Args:
        config: 认证配置
        db_manager: 数据库管理器（可选）

    Returns:
        认证注册中心实例
    """
    global _global_registry

    if _global_registry is None:
        _global_registry = AuthProviderRegistry(config, db_manager)

    return _global_registry


def get_registry() -> Optional[AuthProviderRegistry]:
    """获取全局认证注册中心实例"""
    return _global_registry


def reset_registry() -> None:
    """重置全局认证注册中心"""
    global _global_registry
    if _global_registry:
        import asyncio
        asyncio.create_task(_global_registry.close())
    _global_registry = None
