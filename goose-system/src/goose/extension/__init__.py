"""
Extension Module

Extension management system for the agent.
Reference: goose-rs extension patterns

Extension = 系统级插件 (通过 MCP 协议通信)
- 可以提供 Tools 和 Resources
- 支持多种连接方式（Stdio、HTTP、内置等）

Modules:
- config: Extension 配置类型
- base: Extension 基类和工厂
- manager: Extension 生命周期和 MCP 通信

注意: 以下管理器已在 Agent 级别的 managers/ 目录实现:
- RetryManager - 自动重试
- PermissionManager - 权限管理
- SubagentHandler - 子代理
- PromptManager - 提示模板
- FrontendManager - 前端工具
"""

from .config import (
    ExtensionConfig,
    ExtensionType,
    StdioExtensionConfig,
    SseExtensionConfig,
    StreamableHttpExtensionConfig,
    FrontendExtensionConfig,
    BuiltinExtensionConfig,
    PlatformExtensionConfig,
    InlinePythonExtensionConfig,
    parse_extension_config,
    load_extensions_from_config,
)

from .base import (
    Extension,
    StdioExtension,
    SseExtension,
    HttpExtension,
    FrontendExtension,
    PlatformExtension,
    BuiltinExtension,
    InlinePythonExtension,
    ExtensionFactory,
)

from .manager import (
    ExtensionManager,
)

from .manager_tools import (
    ExtensionManagerTools,
    ExtensionInfo,
    create_extension_manager_tools,
    register_extension_manager_tools,
)

__all__ = [
    # Config
    "ExtensionConfig",
    "ExtensionType",
    "StdioExtensionConfig",
    "SseExtensionConfig",
    "StreamableHttpExtensionConfig",
    "FrontendExtensionConfig",
    "BuiltinExtensionConfig",
    "PlatformExtensionConfig",
    "InlinePythonExtensionConfig",
    "parse_extension_config",
    "load_extensions_from_config",
    # Base
    "Extension",
    "StdioExtension",
    "SseExtension",
    "HttpExtension",
    "FrontendExtension",
    "PlatformExtension",
    "BuiltinExtension",
    "InlinePythonExtension",
    "ExtensionFactory",
    # Manager
    "ExtensionManager",
    # Manager Tools
    "ExtensionManagerTools",
    "ExtensionInfo",
    "create_extension_manager_tools",
    "register_extension_manager_tools",
]
