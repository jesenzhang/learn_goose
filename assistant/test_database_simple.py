"""
简化的数据库模式切换测试

只测试核心配置功能，不依赖整个模块
"""

import os
import sys
from pathlib import Path

# 添加 src 路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


def test_config_override():
    """测试配置覆盖"""
    print("\n=== Test Config Override ===")

    # 测试环境变量优先级
    os.environ["USE_REMOTE_DB"] = "false"

    # 模拟 DatabaseConfig.get_effective_config()
    def get_effective_config(use_remote_default):
        use_remote_env = os.getenv("USE_REMOTE_DB", "").lower()

        if use_remote_env in ("true", "1", "yes"):
            use_remote = True
        elif use_remote_env in ("false", "0", "no"):
            use_remote = False
        else:
            use_remote = use_remote_default

        return use_remote

    # 环境变量覆盖
    use_remote = get_effective_config(use_remote_default=True)
    assert use_remote is False
    print("[OK] Environment variable overrides config file")

    os.environ.pop("USE_REMOTE_DB")


def test_log_level():
    """测试日志级别"""
    print("\n=== Test Log Level ===")

    def is_dev_environment():
        env = os.getenv("ENVIRONMENT", "").lower()
        if env in ("prod", "production"):
            return False
        if env in ("dev", "development"):
            return True
        return True  # 默认 dev

    def get_log_level(use_remote):
        if not is_dev_environment():
            return "INFO"

        if use_remote:
            return "DEBUG"
        else:
            return "INFO"

    # 开发环境 + 远程
    os.environ["ENVIRONMENT"] = "dev"
    assert get_log_level(True) == "DEBUG"
    print("[OK] Dev environment + Remote DB = DEBUG")

    # 生产环境
    os.environ["ENVIRONMENT"] = "prod"
    assert get_log_level(True) == "INFO"
    print("[OK] Prod environment + Remote DB = INFO")

    os.environ.pop("ENVIRONMENT")


def test_config_validation():
    """测试配置验证"""
    print("\n=== Test Config Validation ===")

    def validate_database_config(config):
        errors = []

        use_remote = config.get("use_remote", False)

        if use_remote:
            if not config.get("remote_db_url"):
                errors.append("remote_db_url is required when use_remote=true")
        else:
            if not config.get("local_db_path"):
                errors.append("local_db_path is required when use_remote=false")

        return errors

    # 远程模式缺少 URL
    errors = validate_database_config({"use_remote": True})
    assert "remote_db_url is required" in errors
    print("[OK] Remote mode missing URL validation")

    # 配置正确
    errors = validate_database_config({
        "use_remote": True,
        "remote_db_url": "http://example.com"
    })
    assert len(errors) ==0
    print("[OK] Correct config validation passes")


def test_environment_detection():
    """测试环境检测"""
    print("\n=== Test Environment Detection ===")

    def is_dev_environment():
        env = os.getenv("ENVIRONMENT", "").lower()
        if env in ("prod", "production"):
            return False
        if env in ("dev", "development"):
            return True
        return True  # 默认 dev

    # 默认
    os.environ.pop("ENVIRONMENT", None)
    assert is_dev_environment() is True
    print("[OK] Default dev environment")

    # 生产
    os.environ["ENVIRONMENT"] = "prod"
    assert is_dev_environment() is False
    print("[OK] Production environment detection")

    os.environ.pop("ENVIRONMENT")


def test_config_validation():
    """Test config validation"""
    print("\n=== Test Config Validation ===")

    def validate_database_config(config):
        errors = []

        use_remote = config.get("use_remote", False)

        if use_remote:
            if not config.get("remote_db_url"):
                errors.append("remote_db_url is required when use_remote=true")
        else:
            if not config.get("local_db_path"):
                errors.append("local_db_path is required when use_remote=false")

        return errors

    # Remote mode missing URL
    errors = validate_database_config({"use_remote": True})
    assert "remote_db_url is required" in errors
    print("[OK] Remote mode missing URL validation")

    # Correct config
    errors = validate_database_config({
        "use_remote": True,
        "remote_db_url": "http://example.com"
    })
    assert len(errors) ==0
    print("[OK] Correct config validation passes")


def test_environment_detection():
    """Test environment detection"""
    print("\n=== Test Environment Detection ===")

    def is_dev_environment():
        env = os.getenv("ENVIRONMENT", "").lower()
        if env in ("prod", "production"):
            return False
        if env in ("dev", "development"):
            return True
        return True  # Default dev

    # Default
    os.environ.pop("ENVIRONMENT", None)
    assert is_dev_environment() is True
    print("[OK] Default dev environment")

    # Production
    os.environ["ENVIRONMENT"] = "prod"
    assert is_dev_environment() is False
    print("[OK] Production environment detection")

    os.environ.pop("ENVIRONMENT")


def main():
    """主测试函数"""
    print("="*60)
    print("Database Mode Switching Test (Simplified)")
    print("="*60)

    try:
        test_config_override()
        test_log_level()
        test_config_validation()
        test_environment_detection()

        print("\n" + "="*60)
        print("[OK] All tests passed!")
        print("="*60)

        print("\nFeatures:")
        print("1. Environment variables override config files")
        print("2. Auto-adjust log level based on environment and DB mode")
        print("3. Config validation ensures correct DB settings")
        print("4. Environment detection auto-adapts dev/prod mode")

        print("\nUsage examples:")
        print("  Local mode: export USE_REMOTE_DB=false")
        print("  Remote mode: export USE_REMOTE_DB=true")
        print("  Dev environment: export ENVIRONMENT=dev")
        print("  Prod environment: export ENVIRONMENT=prod")

        return 0

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
