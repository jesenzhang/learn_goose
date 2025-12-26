import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from goose.prompts import get_prompt_manager
from goose.conversation import Message

def test_chat_builder():
    pm = get_prompt_manager()
    
    print("--- 1. Introspection (Variable Check) ---")
    vars_in_task = pm.engine.get_template_variables("task.md")
    print(f"Variables found in 'task.md': {vars_in_task}")
    # 应输出: {'task_objective', 'context_files'}

    print("\n--- 2. Building Full Context ---")
    
    # 模拟历史记录
    history = [
        Message.user("Previous question"),
        Message.assistant("Previous answer")
    ]
    
    # 模拟变量
   # 模拟变量
    context_vars = {
        # [修复] 添加 "parameters": {}，即使是空的也要加，否则模板会报错
        "tools": [{
            "name": "grep", 
            "description": "search file", 
            "parameters": { 
                "type": "object", 
                "properties": {
                    "pattern": {"type": "string"},
                    "file": {"type": "string"}
                }
            }
        }], 
        "task_objective": "Refactor the login module",             
        "context_files": ["login.py", "auth.py"]                   
    }
    # 一键生成所有消息
    messages = pm.create_chat_completion_payload(
        system_template="system.md",
        user_template="task.md",
        history=history,
        variables=context_vars
    )

    print(f"Generated {len(messages)} messages:")
    for i, msg in enumerate(messages):
        role = msg.role.value.upper()
        # 只显示前50个字符预览
        content_preview = msg.as_concat_text().replace('\n', ' ')[:60]
        print(f"[{i}] {role}: {content_preview}...")

if __name__ == "__main__":
    test_chat_builder()