import asyncio
from goose.session import SessionManager
from goose.conversation import Message
from goose.persistence import SQLiteBackend, PersistenceManager

async def main():
    print("🦆 Goose-Py Started (Src Layout)")
    # 1. 初始化底层存储
    backend = SQLiteBackend("app.db")
    PersistenceManager.initialize(backend)
    # 简单的启动测试
    session = await SessionManager.create_session(name="Main Entry Test")
    print(f"Session Created: {session.id}")
    
    await SessionManager.add_message(session.id, Message.user("Hello from src layout!"))
    print("Message added.")
    
    await SessionManager.shutdown()

def run():
    """Entry point for the console script"""
    asyncio.run(main())

if __name__ == "__main__":
    run()