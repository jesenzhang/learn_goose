import asyncio
import os
import sys
import shutil
import logging

# 假设项目路径设置正确
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from goose.persistence import SQLAlchemyBackend, persistence_manager,PersistenceManager
from goose.session.repository import register_session_schemas, SessionRepository
from goose.conversation import Message
from goose.workflow.checkpointer import WorkflowCheckpointRepository,WorkflowCheckpoint
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_persistence")

db_path = "./temp_test_data/test_goose.db"

async def setup_env():
    if os.path.exists("./temp_test_data"):
        shutil.rmtree("./temp_test_data")
    os.makedirs("./temp_test_data", exist_ok=True)

async def main():
    await setup_env()
    print("🚀 Starting Persistence Integration Test...")

    # 1. [Infrastructure] 初始化持久化层
    # 这里我们注入具体的 SQLite 实现
    if not db_path.startswith("sqlite") and "://" not in db_path:
            db_url = f"sqlite+aiosqlite:///{db_path}"
    else:
            db_url = db_path
    backend = SQLAlchemyBackend(db_url)
    pm:PersistenceManager = persistence_manager
    pm.set_backend(backend)

    # 2. [Module Registration] 注册 Session 模块的 Schema
    # 这一步体现了解耦：Session 模块自己决定表结构，主程序负责加载
 
    from goose.persistence.repository import BaseRepository
    print(f"🏠 Test Script BaseRepo ID: {id(BaseRepository)}") # 打印内存地址
    print(f"🧐 Schemas before boot: {BaseRepository.get_all_schemas()}")
    # 3. [Boot] 启动数据库 (建立连接，创建表)
    await pm.boot()
    print("✅ Persistence Layer Booted (Tables Created).")

    workflow_checkpoint_repo = WorkflowCheckpointRepository(pm)
    
    await workflow_checkpoint_repo.save_checkpoint(WorkflowCheckpoint(run_id="test_run", execution_queue=[], context_data={}))
    
    test =await workflow_checkpoint_repo.load_checkpoint("test_run")
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