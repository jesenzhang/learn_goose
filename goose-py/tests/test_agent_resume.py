import asyncio
import os
import sys
import shutil

# 路径设置
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.goose.agent import Agent, AgentStatus
from src.goose.events import EventType
from src.goose.session import SessionManager
from src.goose.tools import ToolRegistry, ShellTool, WriteFileTool
from goose.providers import ModelConfig
from src.goose.providers.openai import OpenAIProvider

# 配置
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"


TEST_WORKSPACE = os.path.abspath("temp_resume_workspace")

async def setup_workspace():
    if os.path.exists(TEST_WORKSPACE):
        shutil.rmtree(TEST_WORKSPACE)
    os.makedirs(TEST_WORKSPACE, exist_ok=True)

async def main():
    print("🚀 Starting Agent Resume/Suspend Test...")
    await setup_workspace()
    
    # 1. 初始化
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.environ["GOOSE_SESSIONS_DIR"] = os.path.join(project_root, "sessions")
    
    registry = ToolRegistry()
    registry.register(WriteFileTool()) # 用于创建文件
    registry.register(ShellTool())     # 用于读取文件
    
    config = ModelConfig(model_name=MODEL_NAME)
    provider = OpenAIProvider(model_config=config, base_url=API_BASE, api_key=API_KEY)
    
    # System Prompt 强调分步执行
    system_prompt = f"""You are Goose. 
    Current dir: {TEST_WORKSPACE}. 
    When asked to do multiple things, do them one by one.
    Use single quotes for code: print('hello').
    """
    
    agent = Agent("Goose-Resume", provider, registry, system_prompt=system_prompt)
    session = await SessionManager.create_session(name="Resume Test")

    task = "First, create a file 'resume.txt' with content 'I am back!'. Then, read the content of 'resume.txt'."
    
    print(f"\n[Round 1] Sending Task: {task}")
    print("⚠️  PLAN: We will CUT THE CONNECTION right after the Agent decides to call the first tool.")
    print("-" * 50)

    original_cwd = os.getcwd()
    os.chdir(TEST_WORKSPACE)
    print(f"📂 CWD switched to: {os.getcwd()}")

    try:
        # --- ROUND 1: 模拟挂起 ---
        tool_call_detected = False
        
        async for event in agent.reply(session.id, user_input=task):
            if event.type == EventType.TEXT:
                print(event.text, end="", flush=True)
                
            elif event.type == EventType.TOOL_CALL:
                print(f"\n\n🛑 [INTERRUPT] Agent wants to call: {event.tool_name}")
                print("🔌 Simulating User/Network interruption... Stopping loop!")
                tool_call_detected = True
                # [关键点] 这里直接 break，不让 Agent 执行工具逻辑
                # 注意：在当前的 Agent 实现中，_main_loop 是后台运行的。
                # 这里 break 只是断开了前端监听。后台 Agent 如果没有等待确认机制，可能会继续跑完。
                # 为了测试 Resume，我们需要确保 Agent 在某一刻停下来。
                # 
                # *如果是纯 Actor 模型*：Agent 会自己跑完。
                # *如果是目前的混合模型*：我们需要 stop Agent。
                await agent.stop() 
                break
        
        if not tool_call_detected:
            print("\n❌ Failed: Agent didn't try to call any tool in Round 1.")
            return

        print("\n" + "=" * 50)
        print("💤 Session is now SUSPENDED. The ToolRequest is in DB, but no ToolResponse yet.")
        print("=" * 50 + "\n")
        
        await asyncio.sleep(2) # 模拟一段时间的延迟

        # --- ROUND 2: 模拟恢复 ---
        print("[Round 2] Resuming Session (Calling reply() with NO input)...")
        print("🔍 Expecting: Agent should detect pending tool, execute it, and then proceed to step 2 (Read file).")
        print("-" * 50)

        # 再次调用 reply，不传 user_input
        async for event in agent.reply(session.id):
            if event.type == EventType.STATE:
                print(f"\n[STATUS] {event.status}")
                
            elif event.type == EventType.TEXT:
                print(event.text, end="", flush=True)
                
            elif event.type == EventType.TOOL_CALL:
                print(f"\n🛠️  [TOOL CALL] {event.tool_name} args={event.tool_args}")
                
            elif event.type == EventType.TOOL_RESULT:
                print(f"\n📋 [RESULT] {event.tool_output.strip()}")

        # 验证文件是否真的被创建了 (证明 Resume 后执行了 Round 1 遗留的工具)
        print("\n" + "=" * 50)
        target_file = os.path.join(TEST_WORKSPACE, "resume.txt")
        if os.path.exists(target_file):
            print("✅ SUCCESS: 'resume.txt' was created!")
            with open(target_file, 'r') as f:
                print(f"📄 Content: {f.read()}")
        else:
            print("❌ FAIL: File was not created.")

    finally:
        # [修复] 恢复目录
        os.chdir(original_cwd)
        print(f"📂 CWD restored to: {os.getcwd()}")
        await SessionManager.shutdown()

    # 验证部分 (现在应该能通过了)
    print("\n" + "=" * 50)
    target_file = os.path.join(TEST_WORKSPACE, "resume.txt")

if __name__ == "__main__":
    asyncio.run(main())