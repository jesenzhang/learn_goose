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
from goose.conversation.message import Message, TextContent
from goose.model import ModelConfig
from goose.providers import OpenAIProvider

# --- 配置区域 (请根据实际情况修改) ---
# vLLM / Qwen / Ollama 配置
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
API_KEY = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
API_BASE = "https://api.siliconflow.cn/v1"
# API_BASE = "http://192.168.10.180:8088/v1/" 
# API_KEY = "vllm"
# MODEL_NAME = "qwen3_vl" 

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
    first_token_received = False

    try:
        # 记录开始时间，用于检查是否是模型太慢
        import time
        start_time = time.time()

        async for msg, usage in provider.stream(system_prompt, history):
            # [调试] 如果超过5秒没反应，打印等待提示
            if not first_token_received and (time.time() - start_time > 5):
                print("(Waiting for model prefill...)...", end="\n", flush=True)
                start_time = time.time() # 重置避免重复打印

            # 1. 处理 Token 统计 (通常在最后，但也可能伴随消息)
            if usage:
                token_usage = usage
                # 如果是纯 Usage 消息，继续下一次循环
                if not msg: 
                    continue

            # 2. 处理消息内容
            if msg and msg.content:
                # 标记已收到首字
                first_token_received = True
                
                # 获取第一个内容块
                content_item = msg.content[0]
                
                # [调试] 如果类型不对，打印类型名以便排查
                if not isinstance(content_item, TextContent):
                    # 可能是 ToolRequest 或 Thinking，打印出来看看
                    print(f"\n[Debug: Non-Text Content: {type(content_item).__name__}]", end="\n", flush=True)
                    continue

                # 正常打印文本
                chunk = content_item.text
                if chunk:
                    # ✅ 修复：只保留这一个 print，去掉原来的第二个 print(chunk, flush=True)
                    print(chunk, end="", flush=True)
                    full_response_text += chunk
            
    except Exception as e:
        import traceback
        print(f"\n\n❌ Error during streaming: {e}")
        traceback.print_exc() # 打印完整堆栈
        
        if "Connection" in str(e):
            print("Tip: Check if your vLLM server URL is correct and accessible.")
        
        await SessionManager.shutdown()
        return

    # 如果循环结束了 full_response_text 还是空的
    if not full_response_text:
        print("\n⚠️ Warning: Stream finished but no text was collected.")
        if token_usage:
            print(f"   (But Usage was received: {token_usage.usage})")
        else:
            print("   (No data received from provider)")

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