import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from goose.agent import Agent, AgentStatus
from goose.events import EventType
from goose.session import SessionManager
from goose.toolkit import ToolRegistry, ShellTool
from goose.providers import ModelConfig
from goose.providers.openai import OpenAIProvider

# 配置
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"

async def main():
    print("🚀 Starting EventBus Agent Test...")
    
    # Init
    registry = ToolRegistry()
    registry.register(ShellTool())
    
    config = ModelConfig(model_name=MODEL_NAME)
    provider = OpenAIProvider(model_config=config, base_url=API_BASE, api_key=API_KEY)
    
    # 锁定 DB
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.environ["GOOSE_SESSIONS_DIR"] = os.path.join(project_root, "sessions")
    import platform
    system_prompt = f"You are a helpful assistant running on {platform.system()}."
    agent = Agent("Goose-Bus", provider, registry, system_prompt=system_prompt)
  
    session = await SessionManager.create_session(name="Bus Test")

    # 1. 启动监听器 (Consumer)
    # 我们用一个单独的 task 来打印日志，模拟 UI 线程
    async def event_listener():
        print("🎧 Listener started waiting for events...")
        async for event in agent.events.subscribe():
            if event.type == EventType.STATE:
                print(f"\n[STATUS CHANGE] -> {event.status}")
                if event.status == AgentStatus.IDLE:
                    print("✅ Agent went Idle. Task Finished.")
                    # 实际业务中可能不退出，而是继续等
                    break 
            elif event.type == EventType.TEXT:
                print(event.text, end="", flush=True)
            elif event.type == EventType.TOOL_CALL:
                print(f"\n🛠️  [TOOL] {event.tool_name} args={event.tool_args}")
            elif event.type == EventType.TOOL_RESULT:
                print(f"\n📋 [RESULT] {event.tool_output}...")
            elif event.type == EventType.ERROR:
                print(f"\n❌ [ERROR] {event.message}")

    listener_task = asyncio.create_task(event_listener())

    # 2. 触发任务 (Producer)
    print("👉 Triggering Agent Process...")
    await agent.process(session.id, user_input="List files in current directory")
    
    # 3. 等待监听结束
    await listener_task
    print("\n👋 Test Done.")

if __name__ == "__main__":
    asyncio.run(main())