import asyncio
import os
import sys
import shutil

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.goose.mcp.client import McpClient
from src.goose.toolkit.mcp_adapter import McpTool
from src.goose.toolkit.registry import ToolRegistry
from src.goose.agent import Agent
from src.goose.providers.openai import OpenAIProvider
from goose.providers import ModelConfig
from src.goose.session import SessionManager

# 配置
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"

async def main():
    print("🚀 Starting MCP Integration Test...")
    
    # 1. 准备 MCP Client (连接 SQLite Server)
    # 我们使用 uvx (Python) 或者 npx (Node) 来启动 Server
    # 请确保您的环境有 npx
    db_file = "test_mcp.db"
    if os.path.exists(db_file): os.remove(db_file)
    
    # 命令拆分：npx -y @modelcontextprotocol/server-sqlite --db-path test_mcp.db
    mcp_cmd = "npx" 
    mcp_args = ["-y", "@modelcontextprotocol/server-sqlite", "--db-path", db_file]
    
    # 如果是 Windows，npx 需要加上 .cmd
    if os.name == 'nt':
        mcp_cmd = "npx.cmd"

    client = McpClient(mcp_cmd, mcp_args)
    
    try:
        await client.connect()
        print("✅ MCP Client Connected!")
        
        # 2. 获取并注册工具
        mcp_tools = await client.list_tools()
        print(f"🛠️  Found {len(mcp_tools)} tools from MCP Server:")
        
        registry = ToolRegistry()
        for tool_def in mcp_tools:
            print(f"   - {tool_def.name}: {tool_def.description[:50]}...")
            adapter = McpTool(client, tool_def)
            registry.register(adapter)
            
        # 3. 启动 Agent
        config = ModelConfig(model_name=MODEL_NAME)
        provider = OpenAIProvider(model_config=config, base_url=API_BASE, api_key=API_KEY)
        
        # 注入 MCP 知识到 System Prompt
        system_prompt = "You are Goose. You have access to a SQLite database via MCP tools. Use them to answer user questions."
        
        agent = Agent("Goose-MCP", provider, registry, system_prompt=system_prompt)
        
        # 4. 执行任务
        session = await SessionManager.create_session(name="MCP Test")
        
        task = "Create a table called 'users' with id and name. Then insert a user 'Goose'. Finally, select all users."
        print(f"\n📝 Task: {task}\n")
        
        async for chunk in agent.reply(session.id, user_input=task):
            # 简单的流式打印，EventBus 模式下需要判断类型
            if isinstance(chunk, str): # 如果还没切到 EventBus，这里是 str
                print(chunk, end="", flush=True)
            elif hasattr(chunk, "text"): # 如果切到了 EventBus
                print(chunk.text, end="", flush=True)
                
    finally:
        await client.close()
        if os.path.exists(db_file):
            os.remove(db_file)
        print("\n👋 Cleanup done.")

if __name__ == "__main__":
    asyncio.run(main())