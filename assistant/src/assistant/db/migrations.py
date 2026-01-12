"""
数据库迁移脚本 - 添加多用户支持

为现有数据库添加 user_id 字段，支持多用户会话管理
"""

import asyncio
import logging
from typing import Optional

from .async_manager import AsyncDatabaseManager

logger = logging.getLogger(__name__)


class DatabaseMigration:
    """数据库迁移管理器"""

    def __init__(self, db_path: str):
        """
        初始化迁移管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.db = AsyncDatabaseManager(db_path)

    async def check_migration_needed(self) -> bool:
        """
        检查是否需要执行迁移

        Returns:
            是否需要迁移
        """
        try:
            conn = await self.db._get_connection()

            # 检查 user_id 列是否存在
            cursor = await conn.execute("PRAGMA table_info(sessions)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            return 'user_id' not in column_names

        except Exception as e:
            logger.error(f"Failed to check migration status: {e}")
            return False

    async def add_user_id_column(self) -> bool:
        """
        添加 user_id 列到 sessions 表

        Returns:
            是否迁移成功
        """
        try:
            conn = await self.db._get_connection()

            # 1. 添加 user_id 列
            logger.info("Adding user_id column to sessions table...")
            await conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")

            # 2. 创建索引
            logger.info("Creating index on user_id...")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user "
                "ON sessions(user_id, updated_at DESC)"
            )

            # 3. 为现有数据设置默认用户
            logger.info("Setting default user_id for existing sessions...")
            await conn.execute(
                "UPDATE sessions SET user_id = 'default' WHERE user_id IS NULL"
            )

            # 4. 提交事务
            await conn.commit()

            logger.info("Migration completed successfully")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=e)
            try:
                await conn.rollback()
            except:
                pass
            return False

    async def migrate(self, default_user: str = "default") -> bool:
        """
        执行迁移

        Args:
            default_user: 为现有会话设置的默认用户 ID

        Returns:
            是否迁移成功
        """
        # 检查是否需要迁移
        if not await self.check_migration_needed():
            logger.info("Database already migrated, skipping")
            return True

        logger.info("Starting database migration for multi-user support...")

        # 执行迁移
        success = await self.add_user_id_column()

        if success:
            logger.info("✅ Multi-user support migration completed")
            return True
        else:
            logger.error("❌ Migration failed")
            return False

    async def rollback(self) -> bool:
        """
        回滚迁移（删除 user_id 列）

        注意：SQLite 不支持直接删除列，需要重建表

        Returns:
            是否回滚成功
        """
        try:
            conn = await self.db._get_connection()

            logger.warning("Rolling back migration (recreating sessions table)...")

            # 1. 创建新表（不含 user_id）
            await conn.execute("""
                CREATE TABLE sessions_new (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. 复制数据
            await conn.execute("""
                INSERT INTO sessions_new (id, state, created_at, updated_at)
                SELECT id, state, created_at, updated_at FROM sessions
            """)

            # 3. 删除旧表
            await conn.execute("DROP TABLE sessions")

            # 4. 重命名新表
            await conn.execute("ALTER TABLE sessions_new RENAME TO sessions")

            # 5. 重建索引
            await conn.execute("DROP INDEX IF EXISTS idx_sessions_user")

            # 6. 提交
            await conn.commit()

            logger.info("Rollback completed successfully")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}", exc_info=e)
            try:
                await conn.rollback()
            except:
                pass
            return False

    async def close(self):
        """关闭数据库连接"""
        await self.db.close()


# ================= 迁移命令 =================

async def migrate_database(db_path: str = "museum_assistant.db") -> bool:
    """
    迁移数据库以支持多用户

    Args:
        db_path: 数据库文件路径

    Returns:
        是否迁移成功

    示例:
        ```python
        from assistant.db.migrations import migrate_database
        success = await migrate_database("museum_assistant.db")
        ```
    """
    migration = DatabaseMigration(db_path)
    try:
        success = await migration.migrate()
        return success
    finally:
        await migration.close()


async def check_migration_status(db_path: str = "museum_assistant.db") -> bool:
    """
    检查迁移状态

    Args:
        db_path: 数据库文件路径

    Returns:
        是否需要迁移

    示例:
        ```python
        from assistant.db.migrations import check_migration_status
        needs_migration = await check_migration_status("museum_assistant.db")
        if needs_migration:
            print("Migration needed")
        ```
    """
    migration = DatabaseMigration(db_path)
    try:
        return await migration.check_migration_needed()
    finally:
        await migration.close()


async def rollback_migration(db_path: str = "museum_assistant.db") -> bool:
    """
    回滚迁移

    注意：这将删除 user_id 列和相关数据

    Args:
        db_path: 数据库文件路径

    Returns:
        是否回滚成功

    示例:
        ```python
        from assistant.db.migrations import rollback_migration
        success = await rollback_migration("museum_assistant.db")
        ```
    """
    migration = DatabaseMigration(db_path)
    try:
        return await migration.rollback()
    finally:
        await migration.close()


# ================= 命令行接口 =================

async def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="数据库迁移工具")
    parser.add_argument(
        "db_path",
        nargs="?",
        default="museum_assistant.db",
        help="数据库文件路径"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查迁移状态"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="回滚迁移"
    )

    args = parser.parse_args()

    if args.check:
        needs_migration = await check_migration_status(args.db_path)
        if needs_migration:
            print("⚠️  Migration needed")
            exit(1)
        else:
            print("✅ Already migrated")
            exit(0)

    elif args.rollback:
        print("⚠️  Rollback will delete user_id column and data!")
        confirm = input("Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled")
            exit(0)

        success = await rollback_migration(args.db_path)
        if success:
            print("✅ Rollback completed")
            exit(0)
        else:
            print("❌ Rollback failed")
            exit(1)

    else:
        # 默认执行迁移
        success = await migrate_database(args.db_path)
        if success:
            print("✅ Migration completed")
            exit(0)
        else:
            print("❌ Migration failed")
            exit(1)


if __name__ == "__main__":
    asyncio.run(main())
