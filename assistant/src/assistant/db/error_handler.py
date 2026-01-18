"""
数据库错误处理器 - 统一处理数据库错误

职责：
- 捕获数据库异常
- 格式化错误消息
- 发送错误事件
- 记录日志（根据环境调整详细程度）
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """数据库错误基类"""

    def __init__(
        self,
        message: str,
        db_mode: str,
        hint: Optional[str] = None,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.db_mode = db_mode
        self.hint = hint
        self.original_exception = original_exception
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """格式化错误消息"""
        parts = [f"[{self.db_mode.upper()} DB] {self.message}"]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        return "\n".join(parts)


def handle_database_error(
    error: Exception,
    db_mode: str,
    event_emitter=None,
    is_dev: bool = True
) -> DatabaseError:
    """
    处理数据库错误

    Args:
        error: 原始异常
        db_mode: 数据库模式 ("remote" 或 "local")
        event_emitter: 事件发射器（可选）
        is_dev: 是否为开发环境

    Returns:
        DatabaseError 对象
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # 1. 记录日志
    if is_dev:
        # 开发环境：详细日志 + 堆栈
        logger.error(
            f"Database error [{error_type}]: {error_msg}",
            exc_info=error
        )
    else:
        # 生产环境：简洁日志
        logger.error(f"Database error [{error_type}]: {error_msg}")

    # 2. 构造提示信息
    hint = None
    if db_mode == "remote":
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            hint = "远程数据库连接超时或失败，建议切换到本地模式：USE_REMOTE_DB=false"
        elif "401" in error_msg or "unauthorized" in error_msg.lower():
            hint = "远程数据库认证失败，请检查 API Key 或 Token"
        elif "403" in error_msg or "forbidden" in error_msg.lower():
            hint = "远程数据库访问被禁止，请检查权限配置"
        elif "404" in error_msg or "not found" in error_msg.lower():
            hint = "远程数据库资源不存在，请检查会话 ID 或 API 端点"
        elif "500" in error_msg or "502" in error_msg or "503" in error_msg:
            hint = "远程数据库服务器错误，请稍后重试或联系管理员"
    else:
        if "lock" in error_msg.lower() or "database is locked" in error_msg.lower():
            hint = "本地数据库被锁定，请检查是否有其他进程正在使用"
        elif "no such table" in error_msg.lower():
            hint = "本地数据库表不存在，请检查数据库文件或重新初始化"
        elif "permission" in error_msg.lower():
            hint = "本地数据库文件权限错误，请检查文件访问权限"
        elif "disk I/O error" in error_msg.lower():
            hint = "本地数据库磁盘 I/O 错误，请检查磁盘空间和权限"

    # 3. 发送错误事件
    if event_emitter:
        try:
            from ..core.events import EventType
            # 注意：这里需要异步调用，但 event_emitter.emit 应该是同步方法
            # 如果需要异步，需要使用 asyncio.create_task
            event_emitter.emit(EventType.ERROR, {
                "error": error_msg,
                "error_type": f"DatabaseError ({db_mode})",
                "hint": hint,
                "db_mode": db_mode,
                "original_exception": error_type
            })
        except Exception as e:
            logger.warning(f"Failed to send error event: {e}")

    # 4. 返回统一错误
    return DatabaseError(
        message=error_msg,
        db_mode=db_mode,
        hint=hint,
        original_exception=error
    )
