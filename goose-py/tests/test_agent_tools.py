import asyncio
import os
import shutil
import platform
import logging
from pathlib import Path
import sys

# 确保导入路径正确
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.goose.model import ModelConfig
from src.goose.providers.openai import OpenAIProvider
from src.goose.session import SessionManager
from src.goose.tools import ToolRegistry, ShellTool, WriteFileTool, ReadFileTool, PatchFileTool
from src.goose.agent import Agent

# 开启 Debug 日志以便观察 SQL 执行
logging.basicConfig(level=logging.INFO)
# logging.getLogger("goose.session").setLevel(logging.DEBUG) 

# --- 配置 ---
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"

TEST_WORKSPACE = os.path.abspath("temp_goose_workspace")

async def setup_workspace():
    if os.path.exists(TEST_WORKSPACE):
        try:
            shutil.rmtree(TEST_WORKSPACE)
        except Exception as e:
            print(f"⚠️ Warning: Failed to clean workspace: {e}")
    os.makedirs(TEST_WORKSPACE, exist_ok=True)
    print(f"📂 Created test workspace: {TEST_WORKSPACE}")

async def main():
    print("\n🤖 Goose-Py Agent Tool Integration Test\n" + "="*50)

    # 1. 环境准备
    await setup_workspace()
    
    # [关键修复] 设置绝对路径的环境变量，防止 os.chdir 导致数据库路径漂移
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sessions_dir = os.path.join(project_root, "sessions")
    os.environ["GOOSE_SESSIONS_DIR"] = sessions_dir
    print(f"🔒 Locked DB Directory to: {sessions_dir}")


    # [关键] 显式初始化 DB 并打印路径
    # 验证一下
    storage = await SessionManager.get_storage()
    print(f"💾 Database Path: {storage.pool.db_path}")

    # 2. 初始化工具
    print("🛠️  Registering Tools...")
    registry = ToolRegistry()
    registry.register(ShellTool()) 
    registry.register(WriteFileTool())
    registry.register(ReadFileTool())
    registry.register(PatchFileTool())

    # 3. 初始化 Provider 和 Agent
    print(f"🔌 Connecting to Model: {MODEL_NAME}")
    config = ModelConfig(model_name=MODEL_NAME, max_tokens=2048)
    provider = OpenAIProvider(model_config=config, base_url=API_BASE, api_key=API_KEY)

    system_prompt = f"""You are Goose, an autonomous coding agent.
You are running on {platform.system()}.
Your current working directory is: {TEST_WORKSPACE}

CRITICAL INSTRUCTIONS:
1. When calling tools, you MUST output strictly valid JSON.
2. **PYTHON CODE TRICK**: When writing Python code inside JSON, use SINGLE QUOTES for strings to avoid escaping hell.
   
   BAD:  {{"content": "print(\"Hello\")"}}  <-- Models often fail this
   GOOD: {{"content": "print('Hello')"}}   <-- Use this!

3. If you must use double quotes inside, ESCAPE THEM: \\"
4. Do not output Markdown blocks.
"""

    agent = Agent(name="Goose-Test", provider=provider, tools=registry, system_prompt=system_prompt)

    # 4. 创建会话
    # [修正] 参数顺序修正：working_dir, name
    print("\nStep 4: Creating Session...")
    session = await SessionManager.create_session(
        working_dir=TEST_WORKSPACE, 
        name="Tool Test Session"
    )
    print(f"✅ Session Created: ID={session.id}, Name={session.name}")
    
    # [关键] 立即验证 Session 是否存在 (排查写入问题)
    try:
        check_session = await SessionManager.get_session(session.id)
        print(f"✅ Session Verification: Found {check_session.id} in DB.")
    except ValueError:
        print("❌ FATAL: Session was created but cannot be found immediately!")
        # 调试：打印 DB 中所有 ID
        async with storage._get_conn() as db:
            async with db.execute("SELECT id, name FROM sessions") as cursor:
                rows = await cursor.fetchall()
                print(f"🔍 Dump of 'sessions' table: {[dict(r) for r in rows]}")
        return

    # 5. 发布任务
    task = """
    Please perform the following task:
    1. Create a python script named 'hello_goose.py' that prints "Hello, Goose!".
    2. Run this script and show me the output.
    3. Use the patch tool to change "Goose" to "World" in that file.
    4. Run the script again to verify the change.
    """
    
    print(f"\n📝 User Task:\n{task}\n")
    print("-" * 50)

    # 6. 运行 Agent
    original_cwd = os.getcwd()
    try:
        # 切换到测试目录，模拟 Agent 在该环境下工作
        os.chdir(TEST_WORKSPACE)
        
        # 此时 SessionManager 依然持有之前打开的 DB 连接 (绝对路径)，所以 chdir 不受影响
        async for event in agent.reply(session.id, user_input=task):
            
            if event.type == "text":
                # 打印 AI 的思考和回复
                text = event.text
                print(text, end="", flush=True)
                
            elif event.type == "tool_call":
                # 打印工具调用详情
                print(f"\n\n🛠️  [CALL] {event.tool_name}")
                print(f"    Args: {event.tool_args}")
                
            elif event.type == "tool_result":
                # 打印工具执行结果 (关键调试信息)
                print(f"\n📋 [RESULT] {event.tool_name}")
                # 截断长输出防止刷屏，但保留足够信息
                output = event.tool_output
                if len(output) > 500:
                    output = output[:500] + "... (truncated)"
                print(f"    Output: {output}")
                
            elif event.type == "error":
                # 打印错误
                print(f"\n❌ [ERROR] {event.message}")
                
            elif event.type == "state":
                # 打印状态变更
                print(f"\n🔄 [STATE] {event.status}")

    except Exception as e:
        import traceback
        print("\n\n❌ Error during execution:")
        traceback.print_exc()
    finally:
        os.chdir(original_cwd)
        # 优雅关闭
        await SessionManager.shutdown()

    print("\n" + "-" * 50)
    
    # 7. 结果验证
    print("\n🔍 Verifying Artifacts...")
    target_file = os.path.join(TEST_WORKSPACE, "hello_goose.py")
    
    if os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"📄 Final File Content:\n{content}")
            
            if "Hello, World!" in content:
                print("\n✅ SUCCESS: File was patched correctly!")
            elif "Hello, Goose!" in content:
                print("\n⚠️ PARTIAL: File created but NOT patched.")
            else:
                print("\n❌ FAIL: Content unexpected.")
        except Exception as e:
            print(f"❌ Error reading file: {e}")
    else:
        print("\n❌ FAIL: File 'hello_goose.py' was not created.")

if __name__ == "__main__":
    asyncio.run(main())