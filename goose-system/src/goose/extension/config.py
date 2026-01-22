"""
Extension 配置和工厂系统

参考: goose-rs/crates/goose/src/agents/extension.rs
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import uuid


class ExtensionType(str, Enum):
    """Extension 类型"""
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"
    BUILTIN = "builtin"
    PLATFORM = "platform"
    INLINE_PYTHON = "inline_python"


class ExtensionConfig(BaseModel):
    """Extension 配置基类"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: ExtensionType
    enabled: bool = True
    timeout: float = 30.0

    class Config:
        populate_by_name = True

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        data = super().model_dump(**kwargs)
        data["type"] = self.type.value if isinstance(self.type, ExtensionType) else self.type
        return data


class StdioExtensionConfig(ExtensionConfig):
    """标准输入/输出扩展配置"""
    type: ExtensionType = ExtensionType.STDIO
    command: str
    args: List[str] = Field(default_factory=list)
    envs: Dict[str, str] = Field(default_factory=dict, alias="env")
    working_dir: Optional[str] = None
    shell: bool = False


class StreamableHttpExtensionConfig(ExtensionConfig):
    """HTTP 流式扩展配置"""
    type: ExtensionType = ExtensionType.STREAMABLE_HTTP
    uri: str
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: float = Field(default=30.0, alias="requestTimeout")
    sse_uri: Optional[str] = None


class BuiltinExtensionConfig(ExtensionConfig):
    """内置扩展配置"""
    type: ExtensionType = ExtensionType.BUILTIN
    module: str
    class_name: str
    config: Dict[str, Any] = Field(default_factory=dict)


class PlatformExtensionConfig(ExtensionConfig):
    """平台扩展配置"""
    type: ExtensionType = ExtensionType.PLATFORM
    platform_name: str = Field(alias="platform")
    config: Dict[str, Any] = Field(default_factory=dict)


class InlinePythonExtensionConfig(ExtensionConfig):
    """内联 Python 扩展配置"""
    type: ExtensionType = ExtensionType.INLINE_PYTHON
    code: str
    dependencies: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)


def parse_extension_config(data: Dict[str, Any]) -> ExtensionConfig:
    """解析 Extension 配置 (支持多种格式)"""
    ext_type = data.get("type", data.get("Type"))

    if ext_type in ["stdio", "Stdio"]:
        return StdioExtensionConfig(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            type=ExtensionType.STDIO,
            enabled=data.get("enabled", True),
            command=data.get("command", ""),
            args=data.get("args", []),
            envs=data.get("env", data.get("envs", {})),
            working_dir=data.get("workingDir"),
            shell=data.get("shell", False),
            timeout=data.get("timeout", 30.0)
        )

    elif ext_type in ["streamable_http", "StreamableHttp"]:
        return StreamableHttpExtensionConfig(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            type=ExtensionType.STREAMABLE_HTTP,
            enabled=data.get("enabled", True),
            uri=data.get("uri", ""),
            headers=data.get("headers", {}),
            timeout=data.get("timeout", data.get("requestTimeout", 30.0)),
            sse_uri=data.get("sseUri")
        )

    elif ext_type in ["builtin", "Builtin"]:
        return BuiltinExtensionConfig(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            type=ExtensionType.BUILTIN,
            enabled=data.get("enabled", True),
            module=data.get("module", ""),
            class_name=data.get("className", data.get("class_name", "")),
            config=data.get("config", {})
        )

    elif ext_type in ["platform", "Platform"]:
        return PlatformExtensionConfig(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            type=ExtensionType.PLATFORM,
            enabled=data.get("enabled", True),
            platform_name=data.get("platform", data.get("platformName", "")),
            config=data.get("config", {})
        )

    elif ext_type in ["inline_python", "InlinePython"]:
        return InlinePythonExtensionConfig(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            type=ExtensionType.INLINE_PYTHON,
            enabled=data.get("enabled", True),
            code=data.get("code", ""),
            dependencies=data.get("dependencies", []),
            env=data.get("env", {})
        )

    raise ValueError(f"Unknown extension type: {ext_type}")


def load_extensions_from_config(
    config_list: List[Dict[str, Any]]
) -> List[ExtensionConfig]:
    """从配置列表加载所有 Extension 配置"""
    return [parse_extension_config(config) for config in config_list]
