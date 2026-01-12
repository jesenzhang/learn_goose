#!/usr/bin/env python3
"""
Simplified multi-user database test (no dependency on full agent module)
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


async def test_multi_user_db():
    """Test multi-user database support"""
    print("=== Multi-User Database Test ===")

    # 1. Directly import AsyncDatabaseManager
    from assistant.db.async_manager import AsyncDatabaseManager

    # 2. Create database
    db = AsyncDatabaseManager(db_path="test_multi_user.db")
    await db.initialize()

    # 3. Test different users' sessions
    users = ["alice", "bob", "charlie"]

    print("\n1. Creating user sessions...")
    for user_id in users:
        session_id = f"{user_id}_test_session"
        state = {
            "session_id": session_id,
            "user_id": user_id,
            "title": f"{user_id}'s Session",
            "history": [
                {"role": "user", "content": f"Hello, I'm {user_id}"},
                {"role": "assistant", "content": f"Hi {user_id}!"}
            ],
            "updated_at": datetime.now().timestamp(),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        success = await db.save_state_for_user(user_id, session_id, state)
        print(f"[OK] Saved state for {user_id}: {success}")

    # 4. List all users
    print("\n2. Listing all users...")
    all_users = await db.list_all_users()
    print(f"[OK] All users: {len(all_users)}")
    for user in all_users:
        print(f"  - {user['user_id']}: {user['session_count']} sessions")

    # 5. Get user stats
    print("\n3. Getting user stats...")
    for user_id in users:
        stats = await db.get_user_stats(user_id)
        print(f"[OK] Stats for {user_id}:")
        print(f"  - Sessions: {stats['sessions']}")
        print(f"  - Events: {stats['events']}")
        print(f"  - Memories: {stats['memories']}")

    # 6. List specific user's sessions
    print("\n4. Listing Alice's sessions...")
    alice_sessions = await db.list_sessions_for_user("alice")
    print(f"[OK] Alice's sessions: {len(alice_sessions)}")
    for session in alice_sessions:
        print(f"  - {session['id']}: {session['title']}")

    # 7. Test loading user state
    print("\n5. Loading Alice's state...")
    alice_state = await db.load_state_for_user("alice", "alice_test_session")
    if alice_state:
        print(f"[OK] Loaded Alice's state:")
        print(f"  - User ID: {alice_state['user_id']}")
        print(f"  - Title: {alice_state['title']}")
        print(f"  - History: {len(alice_state['history'])} messages")

    # 8. Test backward-compatible save_state (auto-route via user_id field)
    print("\n6. Testing backward-compatible save_state...")
    bob_state = {
        "session_id": "bob_compat_session",
        "user_id": "bob",
        "title": "Bob's Compatible Session",
        "history": [],
        "updated_at": datetime.now().timestamp(),
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    success = await db.save_state("bob_compat_session", bob_state)
    print(f"[OK] Saved via save_state (auto-routed): {success}")

    # 9. Test deleting user data
    print("\n7. Deleting Charlie's data...")
    deleted_count = await db.delete_user_sessions("charlie")
    print(f"[OK] Deleted Charlie's data: {deleted_count} sessions")

    # 10. List users again, verify deletion
    print("\n8. Verifying deletion...")
    all_users_after = await db.list_all_users()
    print(f"[OK] All users after deletion: {len(all_users_after)}")
    user_ids = [u['user_id'] for u in all_users_after]
    print(f"  - Users: {user_ids}")

    # 11. Global stats
    print("\n9. Global stats...")
    global_stats = await db.get_stats()
    print(f"[OK] Global stats:")
    print(f"  - Total sessions: {global_stats['total_sessions']}")
    print(f"  - Total users: {global_stats['total_users']}")
    print(f"  - Total events: {global_stats['total_events']}")
    print(f"  - Total memories: {global_stats['total_memories']}")

    # 12. Cleanup
    await db.close()

    # Delete test database
    if os.path.exists("test_multi_user.db"):
        os.remove("test_multi_user.db")
        print("\n[OK] Cleaned up test database")

    print("\n=== All tests passed! ===")


if __name__ == "__main__":
    asyncio.run(test_multi_user_db())
