"""
测试数据库模式切换功能

验证：
1. 环境变量覆盖配置
2. 配置验证
3. 数据库创建
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目路径（指向 src/assistant）
sys.path.insert(0, str(Path(__file__).parent / "src"))

from assistant.config.models import DatabaseConfig
from assistant.db.factory import (
    is_dev_environment,
    get_log_level,
    validate_database_config
)
from assistant.db import UnifiedDatabase


async def test_environment_detection():
    """测试环境检测"""
    print("\n=== 测试环境检测 ===")

    # 默认开发环境
    os.environ.pop("ENVIRONMENT", None)
    assert is_dev_environment() is True
    print("✅ 默认开发环境")

    # 生产环境
    os.environ["ENVIRONMENT"] = "prod"
    assert is_dev_environment() is False
    print("✅ 生产环境检测")

    os.environ.pop("ENVIRONMENT")


async def test_log_level():
    """测试日志级别"""
    print("\n=== 测试日志级别 ===")

    os.environ["ENVIRONMENT"] = "dev"
    assert get_log_level(use_remote=True) == "DEBUG"
    print("✅ 开发环境 + 远程数据库 = DEBUG")

    assert get_log_level(use_remote=False) == "INFO"
    print("✅ 开发环境 + 本地数据库 = INFO")

    os.environ["ENVIRONMENT"] = "prod"
    assert get_log_level(use_remote=True) == "INFO"
    print("✅ 生产环境 + 远程数据库 = INFO")

    os.environ.pop("ENVIRONMENT")


async def test_environment_override():
    """测试环境变量覆盖"""
    print("\n=== 测试环境变量覆盖 ===")

    # 配置文件设置 use_remote=true
    config = DatabaseConfig(use_remote=True, local_db_path="default.db")

    # 环境变量覆盖为 false
    os.environ["USE_REMOTE_DB"] = "false"
    os.environ["LOCAL_DB_PATH"] = "custom.db"

    effective = config.get_effective_config()

    assert effective["use_remote"] is False
    print("✅ USE_REMOTE_DB 环境变量覆盖配置文件")

    assert effective["local_db_path"] == "custom.db"
    print("✅ LOCAL_DB_PATH 环境变量覆盖配置文件")

    # 清理环境变量
    os.environ.pop("USE_REMOTE_DB")
    os.environ.pop("LOCAL_DB_PATH")


async def test_config_validation():
    """测试配置验证"""
    print("\n=== 测试配置验证 ===")

    # 远程模式缺少 URL
    errors = validate_database_config({"use_remote": True})
    assert "remote_db_url is required" in errors
    print("✅ 远程模式缺少 URL 验证")

    # 配置正确
    errors = validate_database_config({
        "use_remote": True,
        "remote_db_url": "http://example.com"
    })
    assert len(errors) == 0
    print("✅ 正确配置验证通过")

    # 本地模式缺少路径
    errors = validate_database_config({"use_remote": False, "local_db_path": None})
    assert "local_db_path is required" in errors
    print("✅ 本地模式缺少路径验证")


async def test_database_creation():
    """测试数据库创建"""
    print("\n=== 测试数据库创建 ===")

    # 测试本地数据库创建
    print("\n--- 测试本地数据库 ---")
    config = DatabaseConfig(use_remote=False, local_db_path=":memory:")

    db = UnifiedDatabase(
        local_db_path=config.local_db_path,
        use_remote=config.use_remote
    )

    await db.initialize()
    print("✅ 本地数据库初始化成功")

    # 健康检查
    healthy = await db.health_check()
    assert healthy is True
    print("✅ 本地数据库健康检查通过")

    # 测试基本操作
    test_state = {"test": "data"}
    result = await db.save_state(1, test_state)
    assert result is True
    print("✅ 保存状态成功")

    loaded = await db.load_state(1)
    assert loaded == test_state
    print("✅ 加载状态成功")

    await db.close()
    print("✅ 数据库关闭成功")


async def test_database_factory():
    """测试数据库工厂"""
    print("\n=== 测试数据库工厂 ===")

    # 测试工厂创建本地数据库
    print("\n--- 测试工厂创建本地数据库 ---")
    os.environ["USE_REMOTE_DB"] = "false"

    config = DatabaseConfig(use_remote=False, local_db_path=":memory:")
    from assistant.db.factory import create_database

    db = await create_database(config)
    assert db.use_remote is False
    print("✅ 工厂创建本地数据库成功")

    # 健康检查
    healthy = await db.health_check()
    assert healthy is True
    print("✅ 工厂健康检查通过")

    await db.close()

    # 清理环境变量
    os.environ.pop("USE_REMOTE_DB")


async def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试错误处理 ===")

    from assistant.db.error_handler import handle_database_error, DatabaseError
    from assistant.core.events import EventType

    # 测试远程数据库错误处理
    print("\n--- 测试远程数据库错误处理 ---")

    # 模拟超时错误
    error = Exception("Connection timeout")
    handled = handle_database_error(
        error=error,
        db_mode="remote",
        event_emitter=None,
        is_dev=True
    )

    assert isinstance(handled, DatabaseError)
    assert handled.db_mode == "remote"
    assert "timeout" in str(handled).lower() or "连接" in str(handled).lower()
    print("✅ 远程数据库超时错误处理")

    # 模拟认证错误
    error = Exception("401 Unauthorized")
    handled = handle_database_error(
        error=error,
        db_mode="remote",
        event_emitter=None,
        is_dev=True
    )

    assert isinstance(handled, DatabaseError)
    assert handled.hint is not None
    assert "认证" in handled.hint
    print("✅ 远程数据库认证错误处理")


async def main():
    """主测试函数"""
    print("="*60)
    print("数据库模式切换功能测试")
    print("="*60)

    try:
        await test_environment_detection()
        await test_log_level()
        await test_environment_override()
        await test_config_validation()
        await test_database_creation()
        await test_database_factory()
        await test_error_handling()

        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)

        print("\n使用示例：")
        print("1. 本地模式：export USE_REMOTE_DB=false")
        print("2. 远程模式：export USE_REMOTE_DB=true")
        print("3. 启动应用：python -m assistant.main")

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
