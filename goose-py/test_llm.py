import asyncio
import os
import sys

# --- 关键设置：适配 src 目录结构 ---
# 这一步确保即使没有运行 'pip install -e .' 也能找到 goose 包
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

print(f"📂 Added source path: {src_path}")

# --- 导入模块 (基于最新的 goose 包结构) ---
from goose.session import SessionManager
from goose.conversation import Message, Role, TextContent
from goose.model import ModelConfig
from goose.providers import OpenAIProvider

# --- 配置区域 (请根据实际情况修改) ---
# vLLM / Qwen / Ollama 配置
API_BASE = "http://192.168.10.180:8088/v1/" 
API_KEY = "vllm"
# 注意：模型名称必须与 vLLM 启动参数或 list_models 返回的一致
MODEL_NAME = "qwen3_vl" 

async def main():
    print("\n🚀 Starting Goose-Py LLM Integration Test (Src Layout)\n")

    # 1. 初始化数据库 (SessionStorage)
    print("Step 1: Initializing Database...")
    # 这会自动运行 migrations 创建表
    await SessionManager.get_storage()
    print("✅ Database initialized.")

    # 2. 创建新会话
    print("\nStep 2: Creating Session...")
    session = await SessionManager.create_session(name="Integration Test Session")
    print(f"✅ Session Created: {session.id} (Type: {session.session_type})")

    # 3. 构造并存储用户消息
    user_query = "请用 Python 写一个 Hello World，并简单解释一下。"
    print(f"\nStep 3: User sends: '{user_query}'")
    
    user_msg = Message.user(user_query)
    await SessionManager.add_message(session.id, user_msg)
    print("✅ User message saved to DB.")

    # 4. 初始化模型提供者 (Provider)
    print(f"\nStep 4: Connecting to Provider ({MODEL_NAME})...")
    config = ModelConfig(
        model_name=MODEL_NAME, 
        temperature=0.7,
        max_tokens=1024
    )
    
    provider = OpenAIProvider(
        model_config=config,
        base_url=API_BASE,
        api_key=API_KEY
    )

    # 5. 获取历史记录 (用于发送给 LLM)
    history = await SessionManager.get_messages(session.id)
    system_prompt = "You are a professional coding assistant named Goose."

    # 6. 流式调用 LLM 并实时输出
    print("\nStep 5: Streaming Response...")
    print("-" * 50)
    
    full_response_text = ""
    token_usage = None

    try:
        async for msg, usage in provider.stream(system_prompt, history):
            # 处理文本增量
            if msg and msg.content:
                # 注意：MessageContent 列表中的第一个元素通常是 TextContent
                content_item = msg.content[0]
                if isinstance(content_item, TextContent):
                    chunk = content_item.text
                    print(chunk, end="", flush=True)
                    full_response_text += chunk
            
            # 处理 Token 统计 (通常在最后返回)
            if usage:
                token_usage = usage
    except Exception as e:
        print(f"\n❌ Error during streaming: {e}")
        # 如果是连接错误，打印提示
        if "Connection" in str(e):
            print("Tip: Check if your vLLM server URL is correct and accessible.")
        await SessionManager.shutdown()
        return

    print("\n" + "-" * 50)

    # 7. 存储 AI 回复
    if full_response_text:
        print("\nStep 6: Saving Assistant Response...")
        ai_msg = Message.assistant(full_response_text)
        await SessionManager.add_message(session.id, ai_msg)
        print("✅ AI response saved.")
    
    # 8. 验证与统计
    print("\nStep 7: Verification")
    if token_usage:
        print(f"📊 Usage Stats: Input={token_usage.usage.input_tokens}, Output={token_usage.usage.output_tokens}")
    
    # 验证数据库中的消息数量
    stored_msgs = await SessionManager.get_messages(session.id)
    print(f"🔍 Messages in DB: {len(stored_msgs)} (Expected >= 2)")
    
    # 9. 清理资源
    await SessionManager.shutdown()
    print("\n🎉 Test Completed Successfully!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")