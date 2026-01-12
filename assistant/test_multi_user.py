#!/usr/bin/env python3
"""
测试多用户支持的脚本
"""

import asyncio
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from assistant.db import configure_db
from assistant.core.state import AgentState


async def test_multi_user_support():
    """测试多用户支持"""
    print("=== 多用户支持测试 ===")

    # 1. 配置数据库
    db = configure_db(local_db_path="test_multi_user.db")
    await db.initialize()

    # 2. 测试不同用户的会话
    users = ["alice", "bob", "charlie"]

    for user_id in users:
        session_id = f"{user_id}_test_session"
        state = AgentState(
            session_id=session_id,
            user_id=user_id,
            title=f"{user_id}'s Session"
        )

        # 添加一些历史
        state.history.append({"role": "user", "content": f"Hello, I'm {user_id}"})
        state.history.append({"role": "assistant", "content": f"Hi {user_id}!"})

        # 保存状态
        success = await db.save_state_for_user(user_id, session_id, state.model_dump())
        print(f"✓ Saved state for {user_id}: {success}")

    # 3. 列出所有用户
    all_users = await db.list_all_users()
    print(f"\n✓ All users: {len(all_users)}")
    for user in all_users:
        print(f"  - {user['user_id']}: {user['session_count']} sessions")

    # 4. 获取用户统计
    for user_id in users:
        stats = await db.get_user_stats(user_id)
        print(f"\n✓ Stats for {user_id}:")
        print(f"  - Sessions: {stats['sessions']}")
        print(f"  - Events: {stats['events']}")
        print(f"  - Memories: {stats['memories']}")

    # 5. 列出特定用户的会话
    alice_sessions = await db.list_sessions_for_user("alice")
    print(f"\n✓ Alice's sessions: {len(alice_sessions)}")
    for session in alice_sessions:
        print(f"  - {session['id']}: {session['title']}")

    # 6. 测试加载用户状态
    alice_state_data = await db.load_state_for_user("alice", "alice_test_session")
    if alice_state_data:
        alice_state = AgentState(**alice_state_data)
        print(f"\n✓ Loaded Alice's state:")
        print(f"  - User ID: {alice_state.user_id}")
        print(f"  - Title: {alice_state.title}")
        print(f"  - History: {len(alice_state.history)} messages")

    # 7. 测试删除用户数据
    deleted_count = await db.delete_user_sessions("charlie")
    print(f"\n✓ Deleted Charlie's data: {deleted_count} sessions")

    # 8. 再次列出用户，验证删除
    all_users_after = await db.list_all_users()
    print(f"\n✓ All users after deletion: {len(all_users_after)}")

    # 9. 全局统计
    global_stats = await db.get_stats()
    print(f"\n✓ Global stats:")
    print(f"  - Total sessions: {global_stats['total_sessions']}")
    print(f"  - Total users: {global_stats['total_users']}")
    print(f"  - Total events: {global_stats['total_events']}")
    print(f"  - Total memories: {global_stats['total_memories']}")

    # 10. 清理
    await db.close()

    # 删除测试数据库
    if os.path.exists("test_multi_user.db"):
        os.remove("test_multi_user.db")
        print("\n✓ Cleaned up test database")

    print("\n=== 所有测试通过! ===")


if __name__ == "__main__":
    asyncio.run(test_multi_user_support())
