"""
数据库工厂 - 负责创建和配置数据库实例

职责：
- 加载配置（支持环境变量覆盖）
- 创建 UnifiedDatabase 实例
- 执行健康检查
- 提供配置验证
"""

import logging
import os
from typing import Optional, List

from .base import DatabaseBase
from .async_manager import AsyncDatabaseManager
from .remote_db import RemoteDatabaseManager

logger = logging.getLogger(__name__)


def is_dev_environment() -> bool:
    """
    判断是否为开发环境

    优先级：
    1. 环境变量 ENVIRONMENT
    2. 默认 dev
    """
    env = os.getenv("ENVIRONMENT", "").lower()
    if env in ("prod", "production"):
        return False
    if env in ("dev", "development"):
        return True
    # 默认为开发环境
    return True


def get_log_level(use_remote: bool) -> str:
    """
    根据环境和数据库模式确定日志级别

    Args:
        use_remote: 是否使用远程数据库

    Returns:
        日志级别字符串 (DEBUG, INFO, WARNING, ERROR)
    """
    if not is_dev_environment():
        return "INFO"

    # 开发环境
    if use_remote:
        return "DEBUG"  # 远程数据库，详细日志便于调试
    else:
        return "INFO"  # 本地数据库，正常日志


def validate_database_config(config: dict) -> List[str]:
    """
    验证数据库配置是否有效

    Args:
        config: 数据库配置字典

    Returns:
        错误消息列表（空列表表示验证通过）
    """
    errors = []

    use_remote = config.get("use_remote", False)

    if use_remote:
        # 远程模式必需配置
        if not config.get("remote_db_url"):
            errors.append("remote_db_url is required when use_remote=true")

        # 警告（不是错误）
        if config.get("remote_db_url", "").startswith("http://"):
            logger.warning("remote_db_url uses HTTP instead of HTTPS for security")

    else:
        # 本地模式必需配置
        if not config.get("local_db_path"):
            errors.append("local_db_path is required when use_remote=false")

    return errors


async def create_database(
    config,
    event_emitter=None
) -> DatabaseBase:
    """
    创建数据库实例（工厂方法）

    流程：
    1. 获取最终配置（考虑环境变量覆盖）
    2. 根据配置创建数据库实例
    3. 初始化数据库
    4. 执行健康检查（如果启用）

    Args:
        config: DatabaseConfig 对象
        event_emitter: 事件发射器（可选，用于发送错误事件）

    Returns:
        DatabaseBase 实例（AsyncDatabaseManager 或 RemoteDatabaseManager）

    Raises:
        RuntimeError: 健康检查失败或配置无效
    """
    # 1. 获取最终配置
    effective_config = config.get_effective_config()
    use_remote = effective_config["use_remote"]

    logger.info(f"Creating database instance (mode={'remote' if use_remote else 'local'})")

    # 2. 验证配置
    errors = validate_database_config(effective_config)
    if errors:
        error_msg = "Database configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 3. 创建数据库实例（直接返回具体实现，不通过 UnifiedDatabase 代理）
    if use_remote:
        db = RemoteDatabaseManager(
            api_base_url=effective_config["remote_db_url"],
            api_key=effective_config["remote_db_api_key"],
            timeout=effective_config["remote_db_timeout"]
        )
    else:
        db = AsyncDatabaseManager(
            db_path=effective_config["local_db_path"]
        )

    # 4. 初始化数据库
    await db.initialize()

    # 5. 健康检查
    if config.health_check_enabled:
        try:
            healthy = await db.health_check()
            if not healthy:
                error_msg = (
                    f"Database health check failed. "
                    f"Mode: {'remote' if use_remote else 'local'}"
                )

                if use_remote:
                    error_msg += f"\nRemote URL: {effective_config['remote_db_url']}"
                    error_msg += "\nSuggestion: Set USE_REMOTE_DB=false to use local database"
                else:
                    error_msg += f"\nLocal Path: {effective_config['local_db_path']}"

                logger.error(error_msg)

                # 发送错误事件
                if event_emitter:
                    from ..core.events import EventType
                    await event_emitter.emit(EventType.ERROR, {
                        "error": error_msg,
                        "error_type": "DatabaseHealthCheckFailed",
                        "db_mode": "remote" if use_remote else "local"
                    })

                raise RuntimeError(error_msg)

            logger.info("Database health check passed")

        except Exception as e:
            error_msg = f"Database health check error: {str(e)}"
            logger.error(error_msg)

            # 发送错误事件
            if event_emitter:
                from ..core.events import EventType
                await event_emitter.emit(EventType.ERROR, {
                    "error": error_msg,
                    "error_type": "DatabaseHealthCheckError",
                    "db_mode": "remote" if use_remote else "local"
                })

            raise

    # 6. 记录日志级别
    log_level = get_log_level(use_remote)
    logger.info(f"Database log level: {log_level}")
    logger.info(f"Environment: {'dev' if is_dev_environment() else 'prod'}")

    return db
