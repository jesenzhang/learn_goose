import asyncio
from goose.session import SessionManager, SessionType
from goose.conversation import Message

async def main():
    print("--- Testing Modular Session ---")
    
    # 1. 创建会话
    session = await SessionManager.create_session(name="Modular Test")
    print(f"Created: {session.id} ({session.session_type})")
    
    # 2. 添加消息
    await SessionManager.add_message(session.id, Message.user("Testing modules"))
    
    # 3. 搜索
    results = await SessionManager.search_history("Testing")
    print(f"Search found {results.total_matches} matches")
    
    await SessionManager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())