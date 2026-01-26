"""
Tool Permission Store

存储和管理工具权限记录。
参考 goose-rs/crates/goose/src/permission/permission_store.rs 实现。
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..conversation.message import ToolRequestContent

logger = logging.getLogger("goose.permission.permission_store")


@dataclass
class ToolPermissionRecord:
    """工具权限记录"""
    tool_name: str
    allowed: bool
    context_hash: str  # 工具参数/上下文的哈希，用于区分类似的调用
    readable_context: Optional[str] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    expiry: Optional[float] = None  # 过期时间戳

    def is_expired(self) -> bool:
        """检查记录是否已过期"""
        if self.expiry is None:
            return False
        return datetime.now().timestamp() > self.expiry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "allowed": self.allowed,
            "context_hash": self.context_hash,
            "readable_context": self.readable_context,
            "timestamp": self.timestamp,
            "expiry": self.expiry,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolPermissionRecord":
        return cls(
            tool_name=data["tool_name"],
            allowed=data["allowed"],
            context_hash=data["context_hash"],
            readable_context=data.get("readable_context"),
            timestamp=data.get("timestamp", datetime.now().timestamp()),
            expiry=data.get("expiry"),
        )


@dataclass
class PermissionConfig:
    """权限配置"""
    always_allow: List[str] = field(default_factory=list)
    ask_before: List[str] = field(default_factory=list)
    never_allow: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "always_allow": self.always_allow,
            "ask_before": self.ask_before,
            "never_allow": self.never_allow,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionConfig":
        return cls(
            always_allow=data.get("always_allow", []),
            ask_before=data.get("ask_before", []),
            never_allow=data.get("never_allow", []),
        )


class ToolPermissionStore:
    """
    工具权限存储

    功能：
    - 检查工具权限（基于上下文哈希）
    - 记录工具权限决策
    - 支持过期权限
    - 持久化到文件
    """

    PERMISSION_FILE = "tool_permissions.json"

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".goose" / "permissions"

        self.config_dir = config_dir
        self.permissions: Dict[str, List[ToolPermissionRecord]] = {}
        self.version = 1

        # 加载已保存的权限
        self._load()

    def _get_file_path(self) -> Path:
        """获取权限文件路径"""
        return self.config_dir / self.PERMISSION_FILE

    def _load(self) -> None:
        """从文件加载权限"""
        file_path = self._get_file_path()

        if not file_path.exists():
            logger.info(f"Permission file not found: {file_path}")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.permissions = {}
            for key, records in data.get("permissions", {}).items():
                self.permissions[key] = [
                    ToolPermissionRecord.from_dict(r) for r in records
                ]

            # 清理过期条目
            self.cleanup_expired()

            logger.info(f"Loaded {len(self.permissions)} permission entries")
        except Exception as e:
            logger.error(f"Failed to load permissions: {e}")
            self.permissions = {}

    def _save(self) -> None:
        """保存权限到文件"""
        try:
            # 确保目录存在
            self.config_dir.mkdir(parents=True, exist_ok=True)

            file_path = self._get_file_path()
            temp_path = file_path.with_suffix(".tmp")

            # 准备数据
            data = {
                "version": self.version,
                "permissions": {
                    key: [r.to_dict() for r in records]
                    for key, records in self.permissions.items()
                }
            }

            # 先写入临时文件
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # 原子性重命名
            temp_path.replace(file_path)

            logger.debug(f"Saved permissions to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save permissions: {e}")

    def _hash_tool_context(self, tool_request: ToolRequestContent) -> str:
        """
        计算工具上下文的哈希

        这有助于识别同一工具在不同上下文中的使用
        """
        tool_call_value = tool_request.tool_call_value
        if tool_call_value and tool_call_value.arguments:
            arguments_str = json.dumps(tool_call_value.arguments, sort_keys=True)
        else:
            arguments_str = ""

        # 使用 SHA-256 哈希
        hasher = hashlib.sha256()
        hasher.update(arguments_str.encode("utf-8"))
        return hasher.hexdigest()[:16]  # 取前16个字符作为短哈希

    def _get_tool_call_value(self, tool_request: ToolRequestContent) -> Optional[Dict[str, Any]]:
        """获取工具调用的值"""
        try:
            value = tool_request.tool_call_value
            if value:
                return {"name": value.name, "arguments": value.arguments}
        except Exception:
            pass
        return None

    def check_permission(self, tool_request: ToolRequestContent) -> Optional[bool]:
        """
        检查工具权限

        Args:
            tool_request: 工具请求

        Returns:
            True 表示允许，False 表示拒绝，None 表示未找到记录
        """
        context_hash = self._hash_tool_context(tool_request)
        tool_call_value = self._hash_tool_context(tool_request)

        if tool_call_value:
            tool_name = tool_call_value.name
        else:
            # 从 to_dict() 尝试获取
            try:
                data = tool_request.tool_call
                tool_name = data.get("value", {}).get("name", "")
            except Exception:
                return None

        key = f"{tool_name}:{context_hash}"
        records = self.permissions.get(key, [])

        # 查找最新的未过期记录
        for record in reversed(records):
            if not record.is_expired():
                return record.allowed

        return None

    def record_permission(
        self,
        tool_request: ToolRequestContent,
        allowed: bool,
        expiry_duration: Optional[float] = None
    ) -> None:
        """
        记录工具权限决策

        Args:
            tool_request: 工具请求
            allowed: 是否允许
            expiry_duration: 过期时长（秒），None 表示永不过期
        """
        context_hash = self._hash_tool_context(tool_request)
        tool_call_value = tool_request.tool_call_value

        if tool_call_value:
            tool_name = tool_call_value.name
            arguments = tool_call_value.arguments
        else:
            # 尝试从工具调用获取
            try:
                data = tool_request.tool_call
                tool_name = data.get("value", {}).get("name", "")
                arguments = data.get("value", {}).get("arguments", {})
            except Exception:
                return

        key = f"{tool_name}:{context_hash}"

        # 计算过期时间
        expiry = None
        if expiry_duration is not None:
            expiry = datetime.now().timestamp() + expiry_duration

        # 创建记录
        record = ToolPermissionRecord(
            tool_name=tool_name,
            allowed=allowed,
            context_hash=context_hash,
            readable_context=self._to_readable_string(tool_name, arguments),
            timestamp=datetime.now().timestamp(),
            expiry=expiry,
        )

        # 添加到列表
对应
        if key not in self.permissions:
            self.permissions[key] = []
        self.permissions[key].append(record)

        # 保存到文件
        self._save()

    def _to_readable_string(self, tool_name: str, arguments: Optional[Dict[str, Any]]) -> str:
        """将工具调用转换为可读字符串"""
        try:
            args_str = json.dumps(arguments, indent=2, ensure_ascii=False) if arguments else "{}"
            return f"{tool_name}({args_str})"
        except Exception:
            return f"{tool_name}(...)"

    def cleanup_expired(self) -> None:
        """清理所有过期的权限记录"""
        now = datetime.now().timestamp()
        changed = False

        # 遍历倒序以便删除
        keys_to_remove = []
        for key, records in self.permissions.items():
            # 保留未过期的记录
            filtered_records = [
                r for r in records if r.expiry is None or r.expiry > now
            ]

            if len(filtered_records) != len(records):
                changed = True

            if filtered_records:
                self.permissions[key] = filtered_records
            else:
                keys_to_remove.append(key)

        # 删除空条目
        for key in keys_to_remove:
            del self.permissions[key]

        if changed:
            self._save()
            logger.info(f"Cleaned up expired permissions")

    def clear(self) -> None:
        """清空所有权限记录"""
        self.permissions.clear()
        self._save()

    def get_summary(self) -> Dict[str, Any]:
        """获取权限摘要"""
        total_records = sum(len(records) for records in self.permissions.values())
        allowed_count = sum(
            1 for records in self.permissions.values()
            for r in records if r.allowed and not r.is_expired()
        )
        denied_count = sum(
            1 for records in self.permissions.values()
            for r in records if not r.allowed and not r.is_expired()
        )

        return {
            "total_keys": len(self.permissions),
            "total_records": total_records,
            "allowed": allowed_count,
            "denied": denied_count,
        }
