import asyncio
import os
import sys
import shutil
import logging

# 假设项目路径设置正确
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.goose.persistence import SQLiteBackend, PersistenceManager
from src.goose.session.repository import register_session_schemas, SessionRepository
from src.goose.conversation import Message

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_persistence")

TEST_DB_PATH = "./temp_test_data/test_goose.db"

async def setup_env():
    if os.path.exists("./temp_test_data"):
        shutil.rmtree("./temp_test_data")
    os.makedirs("./temp_test_data", exist_ok=True)

async def main():
    await setup_env()
    print("🚀 Starting Persistence Integration Test...")

    # 1. [Infrastructure] 初始化持久化层
    # 这里我们注入具体的 SQLite 实现
    backend = SQLiteBackend(TEST_DB_PATH)
    pm = PersistenceManager.initialize(backend)

    # 2. [Module Registration] 注册 Session 模块的 Schema
    # 这一步体现了解耦：Session 模块自己决定表结构，主程序负责加载
    register_session_schemas()

    # 3. [Boot] 启动数据库 (建立连接，创建表)
    await pm.boot()
    print("✅ Persistence Layer Booted (Tables Created).")

    # 4. [Logic] 使用 SessionRepository
    # Repository 内部自动使用 PersistenceManager 获取连接
    repo = SessionRepository()
    
    session_id = "sess_001"
    
    # A. 创建 Session
    print(f"\nCreating Session: {session_id}...")
    await repo.create_session(
        session_id=session_id, 
        name="Integration Test Session", 
        metadata={"user_id": "user_123", "workflow_mode": True}
    )
    
    # Verify Session
    sess_meta = await repo.get_session_metadata(session_id)
    print(f"   -> Read Metadata: {sess_meta}")
    assert sess_meta["id"] == session_id
    assert sess_meta["metadata"]["workflow_mode"] is True

    # B. 添加消息
    print("\nAdding Messages...")
    msg1 = Message.user("Hello Goose!")
    msg2 = Message.assistant("Hello! How can I help you today?")
    
    await repo.add_message(session_id, msg1)
    await repo.add_message(session_id, msg2)
    print("   -> Messages saved.")

    # C. 读取消息
    print("\nReading Messages Back...")
    history = await repo.get_messages(session_id)
    print(f"   -> Loaded {len(history)} messages.")
    
    for m in history:
        print(f"      [{m.role.value}] {m.as_concat_text()}")

    assert len(history) == 2
    assert history[0].content[0].text == "Hello Goose!"
    assert history[1].role.value == "assistant"

    # 5. [Teardown] 关闭
    await pm.shutdown()
    print("\n✅ Test Completed Successfully!")

if __name__ == "__main__":
    asyncio.run(main())