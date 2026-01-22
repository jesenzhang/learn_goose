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
    StreamableHttpExtensionConfig,
    BuiltinExtensionConfig,
    InlinePythonExtensionConfig,
    parse_extension_config,
    load_extensions_from_config,
)

from .base import (
    Extension,
    StdioExtension,
    HttpExtension,
    BuiltinExtension,
    InlinePythonExtension,
    ExtensionFactory,
)

from .manager import (
    ExtensionManager,
)

__all__ = [
    # Config
    "ExtensionConfig",
    "ExtensionType",
    "StdioExtensionConfig",
    "StreamableHttpExtensionConfig",
    "BuiltinExtensionConfig",
    "InlinePythonExtensionConfig",
    "parse_extension_config",
    "load_extensions_from_config",
    # Base
    "Extension",
    "StdioExtension",
    "HttpExtension",
    "BuiltinExtension",
    "InlinePythonExtension",
    "ExtensionFactory",
    # Manager
    "ExtensionManager",
]
