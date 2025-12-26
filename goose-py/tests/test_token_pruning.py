# test_token_pruning.py
import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from goose.prompts import get_prompt_manager
from goose.conversation import Message

def test_pruning():
    pm = get_prompt_manager()
    
    # 1. 模拟长历史 (假设每条消息约 10 tokens)
    long_history = []
    for i in range(20):
        long_history.append(Message.user(f"Old message {i} " * 5)) # 让消息长一点
        long_history.append(Message.assistant(f"Old reply {i} " * 5))

    print(f"📚 Original History Count: {len(long_history)}")
    
    # 2. 设置一个很苛刻的限制 (例如只允许 200 tokens)
    # 这将迫使管理器删除大部分旧消息
    MAX_TOKENS_FOR_HISTORY = 200
    
    # 3. 执行格式化
    pruned = pm.format_history(long_history, max_tokens=MAX_TOKENS_FOR_HISTORY)
    
    print(f"✂️ Pruned History Count: {len(pruned)}")
    
    # 4. 验证内容
    if len(pruned) < len(long_history):
        print("✅ History was truncated.")
        print(f"   First message now: {pruned[0].content[0].text[:20]}...")
        # 应该看到索引较大的 message (比较新的)，而不是 message 0
    else:
        print("❌ History was NOT truncated (check calculation).")

    # 5. 测试完整 Payload 构建
    payload = pm.create_chat_completion_payload(
        system_template="system.md",
        user_template="task.md",
        history=long_history,
        variables={
            "task_objective": "Do something", 
            "tools": []
        },
        max_tokens=500 # 总共只给 500 token
    )
    
    print(f"📦 Final Payload Length: {len(payload)}")
    # Payload = 1 System + N History + 1 User
    # 只要 N < 40，说明截断生效了

if __name__ == "__main__":
    test_pruning()