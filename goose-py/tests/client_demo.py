import requests
import json
import time
import sys
from typing import Callable, Dict, Any, Optional

# --- 配置 ---
BASE_URL = "http://localhost:8200/api/v1"
ADMIN_ID = "admin"
# ⚠️ 请确保这里的 Key 与你服务端日志打印的一致，或者重新复制
ADMIN_KEY = "sk-goose-15f5e8d2c60c5d9e4c08ac924c916a5f" 
TEST_JSON_PATH = r"goose-py/tests/test.json"

def log(msg, icon="ℹ️"):
    print(f"{icon} {msg}")

class GooseStreamer:
    """
    封装 SSE 流式处理、会话管理和挂起恢复逻辑
    """
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.token = None
        self._login(api_key)

    def _login(self, api_key: str):
        """登录换取 JWT"""
        url = f"{self.base_url}/auth/token"
        try:
            resp = self.session.post(url, data={"username": ADMIN_ID, "password": api_key})
            resp.raise_for_status()
            self.token = resp.json()["access_token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            log(f"Authenticated as {ADMIN_ID}", "🔐")
        except Exception as e:
            log(f"Login failed: {e}", "❌")
            # 打印详细错误方便调试
            if hasattr(e, 'response') and e.response:
                print(e.response.text)
            sys.exit(1)

    def _sse_loop(self, url: str, payload: Dict, on_event: Callable[[str, Dict], None]):
        """核心 SSE 循环"""
        log(f"Connecting stream: {url} ...", "📡")
        try:
            with self.session.post(url, json=payload, stream=True) as resp:
                if resp.status_code != 200:
                    log(f"Stream error: {resp.status_code} - {resp.text}", "❌")
                    return

                for line in resp.iter_lines():
                    if line:
                        decoded = line.decode('utf-8')
                        if decoded.startswith("data: "):
                            raw_data = decoded[6:]
                            if raw_data.strip() == "[DONE]": break
                            try:
                                event = json.loads(raw_data)
                                # 回调给上层
                                should_continue = on_event(event.get("type"), event)
                                if should_continue is False:
                                    break
                            except json.JSONDecodeError:
                                log(f"JSON Parse Error: {raw_data}", "⚠️")
        except requests.exceptions.ChunkedEncodingError:
            log("Stream disconnected prematurely", "⚠️")
        except KeyboardInterrupt:
            log("Stream stopped by user", "🛑")

    # ==========================================
    # 👇 核心修改点：适配新的 Execution 路由
    # ==========================================
    def start_workflow(self, wf_id: str, inputs: Dict, on_event: Callable):
        """启动新工作流"""
        # [Change] URL 变更为 /executions/stream (不带 ID)
        url = f"{self.base_url}/executions/stream"
        
        # [Change] workflow_id 放入 Body 中
        payload = {
            "workflow_id": wf_id,
            "inputs": inputs
        }
        self._sse_loop(url, payload, on_event)

    def resume_workflow(self, run_id: str, inputs: Dict, on_event: Callable):
        """恢复挂起的工作流"""
        # Resume 接口保持 /executions/{id}/resume
        url = f"{self.base_url}/executions/{run_id}/resume"
        
        # Resume 时只需要 inputs
        payload = {"inputs": inputs}
        
        log(f"Resuming execution {run_id}...", "▶️")
        self._sse_loop(url, payload, on_event)

    def create_workflow(self, file_path: str) -> str:
        """导入工作流"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Import 接口保持在 workflows 路由下
        resp = self.session.post(f"{self.base_url}/workflows/import", json=data)
        if resp.status_code != 200:
            raise Exception(f"Import failed: {resp.text}")
        return resp.json()['data']['id']

# --- 业务逻辑处理器 ---

class WorkflowHandler:
    def __init__(self, client: GooseStreamer):
        self.client = client
        self.current_run_id = None
        self.is_suspended = False
        self.final_output = None

    def handle_event(self, event_type: str, event: Dict) -> bool:
        """
        事件回调函数
        Return: True (继续监听), False (停止监听)
        """
        node_id = event.get("node_id", "system")
        
        # 1. 记录 Run ID (通常第一个事件包含 trace_id 或从外部获取)
        if not self.current_run_id and event.get("trace_id"):
            self.current_run_id = event["trace_id"]
            # print(f"   [TraceID] {self.current_run_id}")

        # 2. 处理不同事件
        if event_type == "node_start":
            print(f"   🟢 Node Start: {node_id}")
            
        elif event_type == "token":
            # 打字机效果
            print(event.get("text", ""), end="", flush=True)
            
        elif event_type == "node_finish":
            print(f"\n   🏁 Node Finish: {node_id}")
            
        elif event_type == "suspended":
            # [关键] 处理挂起
            print(f"\n\n   ⏸️ WORKFLOW SUSPENDED")
            print(f"   Reason: {event.get('data', {}).get('reason', 'Wait for input')}")
            self.is_suspended = True
            return False # 停止当前监听，转交控制权给主程序处理输入
            
        elif event_type == "workflow_completed":
            self.final_output = event.get("data")
            print(f"\n   ✅ Workflow Completed")
            return False
            
        elif event_type == "error":
            print(f"\n   ❌ Error: {event.get('error')}")
            return False

        return True

# --- 主程序 ---

if __name__ == "__main__":
    # 1. 初始化
    client = GooseStreamer(BASE_URL, ADMIN_KEY)
    
    # 2. 准备工作流
    try:
        wf_id = client.create_workflow(TEST_JSON_PATH)
        log(f"Workflow prepared: {wf_id}", "📝")
    except Exception as e:
        log(f"Workflow creation failed: {e}", "❌")
        sys.exit(1)

    # 3. 运行工作流
    log("Starting workflow...", "🚀")
    handler = WorkflowHandler(client)
    
    # 启动监听
    client.start_workflow(
        wf_id=wf_id, 
        inputs={"query": "Explain Quantum Physics simply."}, 
        on_event=handler.handle_event
    )

    # 4. 处理挂起恢复 (Human-in-the-Loop)
    if handler.is_suspended and handler.current_run_id:
        # 模拟：此处可以是 CLI 输入，也可以是前端弹窗等待
        user_input = input("\n🤖 Workflow paused. Enter command to resume: ")
        
        # 恢复执行 (会话恢复)
        # 重新建立 SSE 连接
        log("Resuming session...", "🔄")
        
        # 重置状态，复用 handler
        handler.is_suspended = False
        
        client.resume_workflow(
            run_id=handler.current_run_id,
            inputs={"user_feedback": user_input}, # 注入用户输入
            on_event=handler.handle_event
        )

    if handler.final_output:
        print("\n" + "="*30)
        # 美化打印结果
        try:
            print("Final Result:", json.dumps(handler.final_output, indent=2, ensure_ascii=False))
        except:
            print("Final Result:", handler.final_output)
        print("="*30)