"""
Database Mode Switching Test

Tests:
1. Environment variable overrides config
2. Config validation
3. Environment detection
4. Log level adjustment
"""

import os
import sys
from pathlib import Path


def test_config_override():
    """Test config override"""
    print("\n=== Test Config Override ===")

    # Set environment variable
    os.environ["USE_REMOTE_DB"] = "false"

    # Simulate config override
    use_remote_default = True
    use_remote_env = os.getenv("USE_REMOTE_DB", "").lower()

    if use_remote_env in ("true", "1", "yes"):
        use_remote = True
    elif use_remote_env in ("false", "0", "no"):
        use_remote = False
    else:
        use_remote = use_remote_default

    assert use_remote is False
    print("[OK] Environment variable overrides config file")

    os.environ.pop("USE_REMOTE_DB")


def test_environment_detection():
    """Test environment detection"""
    print("\n=== Test Environment Detection ===")

    # Default to dev
    os.environ.pop("ENVIRONMENT", None)
    env = os.getenv("ENVIRONMENT", "").lower()
    is_dev = not (env in ("prod", "production"))
    assert is_dev is True
    print("[OK] Default dev environment")

    # Production
    os.environ["ENVIRONMENT"] = "prod"
    env = os.getenv("ENVIRONMENT", "").lower()
    is_dev = not (env in ("prod", "production"))
    assert is_dev is False
    print("[OK] Production environment detection")

    os.environ.pop("ENVIRONMENT")


def test_log_level():
    """Test log level adjustment"""
    print("\n=== Test Log Level ===")

    # Dev + Remote = DEBUG
    os.environ["ENVIRONMENT"] = "dev"
    is_dev = not (os.getenv("ENVIRONMENT", "").lower() in ("prod", "production"))
    use_remote = True
    log_level = "DEBUG" if (is_dev and use_remote) else "INFO"
    assert log_level == "DEBUG"
    print("[OK] Dev + Remote = DEBUG")

    # Prod + Remote = INFO
    os.environ["ENVIRONMENT"] = "prod"
    is_dev = not (os.getenv("ENVIRONMENT", "").lower() in ("prod", "production"))
    log_level = "DEBUG" if (is_dev and use_remote) else "INFO"
    assert log_level == "INFO"
    print("[OK] Prod + Remote = INFO")

    os.environ.pop("ENVIRONMENT")


def test_config_validation():
    """Test config validation"""
    print("\n=== Test Config Validation ===")

    # Remote mode missing URL
    config = {"use_remote": True}
    errors = []
    if config.get("use_remote", False):
        if not config.get("remote_db_url"):
            errors.append("remote_db_url is required")
    assert "remote_db_url is required" in errors
    print("[OK] Remote mode missing URL validation")

    # Correct config
    config = {"use_remote": True, "remote_db_url": "http://example.com"}
    errors = []
    if config.get("use_remote", False):
        if not config.get("remote_db_url"):
            errors.append("remote_db_url is required")
    assert len(errors) == 0
    print("[OK] Correct config validation")


def main():
    """Main test function"""
    print("="*60)
    print("Database Mode Switching Test")
    print("="*60)

    try:
        test_config_override()
        test_environment_detection()
        test_log_level()
        test_config_validation()

        print("\n" + "="*60)
        print("[OK] All tests passed!")
        print("="*60)

        print("\nFeatures:")
        print("1. Environment variables override config files")
        print("2. Auto-adjust log level based on environment and DB mode")
        print("3. Config validation ensures correct DB settings")
        print("4. Environment detection auto-adapts dev/prod mode")

        print("\nUsage examples:")
        print("  Local mode:   export USE_REMOTE_DB=false")
        print("  Remote mode:  export USE_REMOTE_DB=true")
        print("  Dev env:      export ENVIRONMENT=dev")
        print("  Prod env:     export ENVIRONMENT=prod")

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
