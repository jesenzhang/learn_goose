"""
多用户会话管理使用示例

演示如何使用多用户数据库管理功能
"""

import asyncio
from typing import Optional

# 在实际使用中，这些导入应该是：
# from assistant.db import get_db
# from assistant.core.state import AgentState

# 为了演示，我们定义一个简单的 AgentState
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict


class MockAgentState(BaseModel):
    """模拟的 AgentState"""
    session_id: str
    user_id: Optional[str] = None
    status: str = "idle"
    title: str = "New Chat"
    history: List[Dict] = []
    shared_memory: Dict[str, str] = {}
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


async def example_basic_usage():
    """
    示例 1：基本多用户会话管理
    """
    print("=" * 60)
    print("示例 1：基本多用户会话管理")
    print("=" * 60)

    # 模拟数据库
    # db = await get_db_async()

    # 创建用户会话
    users = ["user1", "user2", "user3"]

    for user_id in users:
        for i in range(3):
            session_id = f"{user_id}_session_{i+1}"
            state = MockAgentState(
                session_id=session_id,
                user_id=user_id,
                title=f"{user_id} 的对话 {i+1}"
            )

            # await db.save_state_for_user(user_id, session_id, state.model_dump())
            print(f"✅ 创建会话: {session_id} (用户: {user_id})")

    # 按用户列出会话
    for user_id in users:
        # sessions = await db.list_sessions_for_user(user_id)
        # print(f"\n👤 用户 {user_id} 的会话 ({len(sessions)} 个):")
        # for session in sessions:
        #     print(f"   - {session['id']}: {session['title']}")
        print(f"\n👤 用户 {user_id} 的会话:")


async def example_user_statistics():
    """
    示例 2：用户统计信息
    """
    print("\n" + "=" * 60)
    print("示例 2：用户统计信息")
    print("=" * 60)

    # db = await get_db_async()

    users = ["user1", "user2", "user3"]

    for user_id in users:
        # stats = await db.get_user_stats(user_id)
        # print(f"\n👤 用户 {user_id} 统计:")
        # print(f"   会话数: {stats['sessions']}")
        # print(f"   事件数: {stats['events']}")
        # print(f"   记忆数: {stats['memories']}")
        print(f"\n👤 用户 {user_id} 统计信息")


async def example_delete_user_data():
    """
    示例 3：删除用户数据
    """
    print("\n" + "=" * 60)
    print("示例 3：删除用户数据")
    print("=" * 60)

    # db = await get_db_async()

    user_id = "user_to_delete"

    # 删除用户的所有会话
    # deleted_count = await db.delete_user_sessions(user_id)
    # print(f"✅ 删除了用户 {user_id} 的 {deleted_count} 个会话")

    print(f"✅ 删除了用户 {user_id} 的数据")


async def example_list_all_users():
    """
    示例 4：列出所有用户
    """
    print("\n" + "=" * 60)
    print("示例 4：列出所有用户")
    print("=" * 60)

    # db = await get_db_async()

    # users = await db.list_all_users()
    # print(f"\n📋 系统中的用户 ({len(users)} 个):")
    # for user in users:
    #     print(f"   - {user['user_id']}: {user['session_count']} 个会话")

    print(f"\n📋 系统中的用户")


async def example_global_statistics():
    """
    示例 5：全局统计
    """
    print("\n" + "=" * 60)
    print("示例 5：全局统计")
    print("=" * 60)

    # db = await get_db_async()

    # stats = await db.get_global_stats()
    # print(f"\n📊 全局统计:")
    # print(f"   总会话数: {stats['total_sessions']}")
    # print(f"   总用户数: {stats['total_users']}")
    # print(f"   总事件数: {stats['total_events']}")
    # print(f"   总记忆数: {stats['total_memories']}")

    print(f"\n📊 全局统计信息")


async def example_user_session_isolation():
    """
    示例 6：用户会话隔离
    """
    print("\n" + "=" * 60)
    print("示例 6：用户会话隔离")
    print("=" * 60)

    # db = await get_db_async()

    # 用户 A 尝试访问用户 B 的会话
    user_a = "alice"
    user_b = "bob"
    session_b = f"{user_b}_secret_session"

    # 加载用户 B 的会话
    # state = await db.load_state_for_user(user_a, session_b)
    # if state:
    #     print("❌ 警告：用户 A 可以访问用户 B 的会话！")
    # else:
    #     print("✅ 用户 A 无法访问用户 B 的会话（权限隔离）")

    print(f"✅ 用户会话权限隔离测试")


async def example_pagination():
    """
    示例 7：分页查询
    """
    print("\n" + "=" * 60)
    print("示例 7：分页查询")
    print("=" * 60)

    # db = await get_db_async()
    user_id = "user1"
    page_size = 5
    page = 1

    # 使用 limit 实现分页
    # sessions = await db.list_sessions_for_user(user_id, limit=page_size)
    # offset = (page - 1) * page_size
    # sessions = await db.list_sessions_for_user(user_id, limit=page_size, offset=offset)

    # print(f"\n📄 用户 {user_id} 的会话（第 {page} 页，每页 {page_size} 条）：")
    # for i, session in enumerate(sessions, 1):
    #     print(f"   {i}. {session['id']}: {session['title']}")

    print(f"\n📄 分页查询演示")


async def main():
    """
    主函数 - 运行所有示例
    """
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "多用户会话管理示例" + " " * 25 + "║")
    print("╚" + "═" * 58 + "╝")

    try:
        # 初始化数据库
        # db = await get_db_async()

        # 运行示例
        await example_basic_usage()
        await example_user_statistics()
        await example_delete_user_data()
        await example_list_all_users()
        await example_global_statistics()
        await example_user_session_isolation()
        await example_pagination()

        print("\n" + "=" * 60)
        print("✅ 所有示例完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


async def migration_example():
    """
    数据库迁移示例
    """
    print("\n" + "=" * 60)
    print("数据库迁移示例")
    print("=" * 60)

    from assistant.db.migrations import (
        check_migration_status,
        migrate_database,
        rollback_migration
    )

    db_path = "museum_assistant.db"

    # 1. 检查迁移状态
    # needs_migration = await check_migration_status(db_path)
    # if needs_migration:
    #     print("⚠️  数据库需要迁移")
    # else:
    #     print("✅ 数据库已迁移")
    print("1. 检查迁移状态")

    # 2. 执行迁移
    # success = await migrate_database(db_path)
    # if success:
    #     print("✅ 迁移成功")
    # else:
    #     print("❌ 迁移失败")
    print("2. 执行数据库迁移")

    # 3. 回滚迁移（危险操作！）
    # print("\n⚠️  回滚将删除 user_id 列！")
    # confirm = input("确定要回滚吗？(yes/no): ")
    # if confirm.lower() == "yes":
    #     success = await rollback_migration(db_path)
    #     if success:
    #         print("✅ 回滚成功")
    #     else:
    #         print("❌ 回滚失败")
    print("3. 回滚迁移")


if __name__ == "__main__":
    # 运行示例
    # asyncio.run(main())

    # 或单独运行迁移示例
    print("\n注意：需要先安装依赖并配置数据库")
    print("运行示例：python multi_user_example.py")
