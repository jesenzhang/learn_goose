import asyncio
import os
import sys

# 确保路径正确
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.goose.mcp.client import McpClient
from src.goose.tools.mcp_adapter import McpToolAdapter
from src.goose.tools.registry import ToolRegistry
from src.goose.agent import Agent
from src.goose.providers.openai import OpenAIProvider
from src.goose.model import ModelConfig
from src.goose.session import SessionManager

# 配置
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"

async def main():
    print("🚀 Starting Simple MCP Test (Python Calculator)...")
    
    # 1. 准备 MCP Client
    # 指向我们刚刚创建的 mock_mcp_server.py
    server_script = os.path.join(os.path.dirname(__file__), "mock_mcp_server.py")
    
    # 命令: python tests/mock_mcp_server.py
    client = McpClient("python", [server_script])
    
    try:
        await client.connect()
        print("✅ Mock MCP Server Connected!")
        
        # 2. 注册工具
        mcp_tools = await client.list_tools()
        print(f"🛠️  Tools found: {[t.name for t in mcp_tools]}")
        
        registry = ToolRegistry()
        for tool_def in mcp_tools:
            adapter = McpToolAdapter(client, tool_def)
            registry.register(adapter)
            
        # 3. 启动 Agent
        config = ModelConfig(model_name=MODEL_NAME)
        provider = OpenAIProvider(model_config=config, base_url=API_BASE, api_key=API_KEY)
        
        # 简单的 Prompt
        system_prompt = "You are a helpful assistant. You have access to a calculator tool."
        
        agent = Agent("Goose-Calc", provider, registry, system_prompt=system_prompt)
        
        # 4. 执行任务
        # 我们用一个稍微复杂的数学题，强制它调用工具
        task = "Calculate 123.45 + 987.65, and then tell me the result."
        
        print(f"\n📝 Task: {task}\n")
        
        # 创建临时 Session
        session = await SessionManager.create_session(name="Simple MCP Test")
        
        # 锁定 DB 目录 (防止您之前的 CWD 问题)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        os.environ["GOOSE_SESSIONS_DIR"] = os.path.join(project_root, "sessions")
        
        async for chunk in agent.reply(session.id, user_input=task):
            if hasattr(chunk, "text"): # EventBus Mode
                 print(chunk.text, end="", flush=True)
            elif isinstance(chunk, str): # Legacy Mode
                 print(chunk, end="", flush=True)
                
    finally:
        await client.close()
        print("\n👋 Test finished.")

if __name__ == "__main__":
    asyncio.run(main())