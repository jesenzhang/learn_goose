import requests
import json
import time
import sys
from typing import Callable, Dict, Any, Optional

# ==========================================
# ⚙️ 配置区域
# ==========================================
BASE_URL = "http://localhost:8200/api/v1"
ADMIN_ID = "admin"
# ⚠️ 请确保这里的 Key 与服务端日志一致
ADMIN_KEY = "sk-goose-15f5e8d2c60c5d9e4c08ac924c916a5f" 
TEST_JSON_PATH = r"goose-py/tests/test.json"

def log(msg, icon="ℹ️"):
    print(f"{icon} {msg}")

# ==========================================
# 📡 GooseStreamer: 负责网络通信
# ==========================================
class GooseStreamer:
    """
    封装 SSE 流式处理、认证、会话管理
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
        except Exception as e:
            log(f"Unexpected error: {e}", "❌")

    def create_workflow(self, file_path: str) -> str:
        """导入工作流"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 接口: /workflows/import
        resp = self.session.post(f"{self.base_url}/workflows/import", json=data)
        if resp.status_code != 200:
            raise Exception(f"Import failed: {resp.text}")
        return resp.json()['data']['id']

    def run_workflow(self, wf_id: str, inputs: Dict):
        """模式 A: 运行新任务"""
        url = f"{self.base_url}/executions/run"
        
        payload = {
            "workflow_id": wf_id,
            "inputs": inputs,
            "after_seq_id": -1
        }
        resp = self.session.post(url, json=payload)
        execution_id = resp.json()['data']['execution_id']
        return execution_id
        
    def listen_to_existing_run(self, run_id: str, on_event: Callable):
        """模式 B: 监听已存在的任务"""
        # GET 请求，参数在 query params 中
        url = f"{self.base_url}/executions/{run_id}/events?after_seq_id=-1"
        
        # 这里不需要 payload，因为是 GET
        log(f"Listening to existing run: {run_id} ...", "🎧")
        
        # 复用 SSE Loop 逻辑，但要改为 GET 方法
        try:
            # 注意：requests.get 而不是 post
            with self.session.get(url, stream=True) as resp:
                if resp.status_code != 200:
                    log(f"Stream error: {resp.status_code} - {resp.text}", "❌")
                    return
                # ... 下面处理逻辑和 _sse_loop 一样 ...
                for line in resp.iter_lines():
                    if line:
                        decoded = line.decode('utf-8')
                        if decoded.startswith("data: "):
                            raw_data = decoded[6:]
                            try:
                                event = json.loads(raw_data)
                                if on_event(event.get("type"), event) is False:
                                    break
                            except: pass
        except Exception as e:
            log(f"Error: {e}", "❌")
            
    def start_workflow(self, wf_id: str, inputs: Dict, on_event: Callable, from_beginning: bool = True):
        """
        启动新工作流
        :param from_beginning: True 表示请求服务端回填历史事件 (after_seq_id=-1)，解决竞态丢失 Token 问题
        """
        url = f"{self.base_url}/executions/stream"
        
        payload = {
            "workflow_id": wf_id,
            "inputs": inputs,
            # [关键] 告诉服务端我们需要所有事件，包括连接前产生的
            "after_seq_id": -1 if from_beginning else None
        }
        self._sse_loop(url, payload, on_event)

    def resume_workflow(self, run_id: str, inputs: Dict, on_event: Callable):
        """恢复挂起的工作流"""
        url = f"{self.base_url}/executions/{run_id}/resume"
        
        # Resume 时通常也是需要回填历史的，或者从断点继续
        # 这里简化为只传 inputs，服务端逻辑决定从哪开始
        payload = {"inputs": inputs}
        
        log(f"Resuming execution {run_id}...", "▶️")
        self._sse_loop(url, payload, on_event)

# ==========================================
# 🧠 WorkflowHandler: 业务逻辑回调
# ==========================================
class WorkflowHandler:
    def __init__(self, client: GooseStreamer):
        self.client = client
        self.current_run_id = None
        self.is_suspended = False
        self.final_output = None
        self.buffer = "" # 用于累积输出

    def handle_event(self, event_type: str, event: Dict) -> bool:
        """
        事件回调函数
        Return: True (继续监听), False (停止监听)
        """
        node_id = event.get("node_id", "system")
        
        # 1. 自动捕获 Run ID
        if not self.current_run_id and event.get("trace_id"):
            self.current_run_id = event["trace_id"]
            # print(f"   [TraceID] {self.current_run_id}")

        print(f"   [Event] {event_type} {str(event)}")
        # 2. 处理各类事件
        if event_type == "node_start":
            print(f"\n   🟢 Node Start: {node_id}")
            
        elif event_type == "stream_token":
            # 打字机效果核心
            text = event.get("text", "")
            print(text, end="", flush=True)
            self.buffer += text
            
        elif event_type == "tool_call":
            print(f"\n   tool_call: {node_id}")
            print(f"   tool_name: {event.get('data', {}).get('tool_name')}")
            print(f"   tool_args: {event.get('data', {}).get('tool_args')}")
            
        elif event_type == "tool_result":
            print(f"\n   tool_result: {node_id}")
        
        elif event_type == "node_finish":
            print(f"\n   🏁 Node Finish: {node_id}")
            
        elif event_type == "suspended":
            # [关键] 遇到挂起信号，暂停监听
            print(f"\n\n   ⏸️ WORKFLOW SUSPENDED")
            print(f"   Reason: {event.get('data', {}).get('reason', 'Wait for input')}")
            self.is_suspended = True
            return False # 断开 SSE 连接，把控制权交回主循环
        elif event_type == "workflow_started":
            self.final_output = event.get("data")
            print(f"\n   ✅ Workflow Completed")
            return False
        elif event_type == "workflow_completed":
            self.final_output = event.get("data")
            print(f"\n   ✅ Workflow Completed")
            return False
        
        elif event_type == "workflow_failed":
             print(f"\n   ❌ Workflow Failed: {event.get('data')}")
             return False
            
        elif event_type == "error":
            print(f"\n   ❌ Error: {event.get('error')}")
            return False

        return True

# ==========================================
# 🚀 主程序入口
# ==========================================
if __name__ == "__main__":
    # 1. 初始化客户端
    client = GooseStreamer(BASE_URL, ADMIN_KEY)
    
    # 2. 准备工作流 (导入 JSON)
    try:
        wf_id = client.create_workflow(TEST_JSON_PATH)
        log(f"Workflow prepared: {wf_id}", "📝")
    except Exception as e:
        log(f"Workflow creation failed: {e}", "❌")
        # 如果文件不存在，请先创建 test.json
        sys.exit(1)

    # 3. 运行工作流 (初始运行)
    log("Starting workflow...", "🚀")
    handler = WorkflowHandler(client)
    
    # 启动监听 (from_beginning=True 确保不丢 Token)
    run_id = client.run_workflow(
        wf_id=wf_id, 
        inputs={"query": "Explain Quantum Physics simply."}
    )

    client.listen_to_existing_run(run_id, handler.handle_event)
    
    # 4. 挂起/恢复 循环 (支持多次挂起)
    while handler.is_suspended and handler.current_run_id:
        # 获取用户输入
        try:
            user_input = input("\n🤖 Workflow paused. Enter command to resume: ")
        except KeyboardInterrupt:
            break
        
        log("Resuming session...", "🔄")
        
        # 重置挂起标志，准备接收新一轮事件
        handler.is_suspended = False
        
        # 调用 Resume 接口
        client.resume_workflow(
            run_id=handler.current_run_id,
            inputs={"user_feedback": user_input}, # 将用户输入注入上下文
            on_event=handler.handle_event
        )

    # 5. 打印最终结果
    if handler.final_output:
        print("\n" + "="*40)
        try:
            print("Final Result:", json.dumps(handler.final_output, indent=2, ensure_ascii=False))
        except:
            print("Final Result:", handler.final_output)
        print("="*40)