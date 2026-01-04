import requests
import json
import time

# 配置
BASE_URL = "http://localhost:8200/api/v1"
ADMIN_ID = "admin"
# 请替换为你日志中打印出来的那个 Key，或者数据库里的 Key
# 如果你是第一次启动，日志里搜 "Created default admin"
ADMIN_KEY = "sk-goose-15f5e8d2c60c5d9e4c08ac924c916a5f" 

def print_step(step):
    print(f"\n{'='*10} {step} {'='*10}")
    
TEST_JSON_PATH = r"goose-py/tests/test.json"


class GooseClient:
    def __init__(self):
        self.session = requests.Session()
        self.token = None

    def login(self):
        """1. 获取 JWT Token"""
        print_step("🔐 Logging in")
        url = f"{BASE_URL}/auth/token"
        # OAuth2 标准表单: username=user_id, password=api_key
        payload = {
            "username": ADMIN_ID,
            "password": ADMIN_KEY
        }
        try:
            resp = self.session.post(url, data=payload)
            resp.raise_for_status()
            data = resp.json()
            self.token = data["access_token"]
            # 设置后续请求的全局 Header
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            print(f"✅ Login Success! Token: {self.token[:15]}...")
        except Exception as e:
            print(f"❌ Login Failed: {e}")
            if resp: print(resp.text)
            exit(1)

    def test_single_node(self):
        """2. 测试单个节点 (Unit Test Mode)"""
        print_step("🧪 Testing Single Node (No DB)")
        url = f"{BASE_URL}/executions/node/test"
        
        payload = {
            "node_type": "model.llm",
            "config": {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                # 这里的 {{query}} 会被 inputs 替换
                "prompt": "You are a helpful assistant. Please echo this: {{query}}"
            },
            "inputs": {
                "query": "Hello Goose Engine!"
            },
            "mock_context": {
                "user_name": "Tester"
            }
        }
        
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            print(f"✅ Node Output: {json.dumps(result['data'], indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"❌ Node Test Failed: {resp.text}")

    def create_workflow(self):
        """3. 创建一个简单的工作流"""
        print_step("📝 Creating Workflow")
        
        with open(TEST_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        workflow_def = data
        resp = self.session.post(f"{BASE_URL}/workflows/import", json={"data":workflow_def})
        data = resp.json()
        wf_id = data['data']['id']
        print(f"✅ Workflow Created: {wf_id}")
        return wf_id

    def run_workflow_stream(self, wf_id):
        """4. 流式运行工作流 (SSE)"""
        print_step("🚀 Running Workflow (Streaming)")
        
        url = f"{BASE_URL}/executions/{wf_id}/stream"
        payload = {
            "inputs": {
                "input_query": "What is the capital of France?"
            }
        }
        
        # stream=True 是关键
        with self.session.post(url, json=payload, stream=True) as resp:
            print("Listening for events...")
            for line in resp.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        event_json = decoded_line[6:] # 去掉 'data: ' 前缀
                        try:
                            event = json.loads(event_json)
                            event_type = event.get("type")
                            
                            # 简单的日志打印
                            if event_type == "node_start":
                                print(f"  [Node Start] {event['node_id']}")
                            elif event_type == "token":
                                # 打印打字机效果 (不换行)
                                print(event['text'], end="", flush=True)
                            elif event_type == "node_finish":
                                print(f"\n  [Node Finish] {event['node_id']}")
                            elif event_type == "workflow_completed":
                                print(f"\n✅ Workflow Completed! Output: {event.get('data')}")
                            elif event_type == "error":
                                print(f"\n❌ Error: {event.get('error')}")
                        except:
                            print(f"Unknown: {decoded_line}")

if __name__ == "__main__":
    client = GooseClient()
    
    # 1. 先去 logs 找一下 API Key 填到上面的 ADMIN_KEY 里
    # 2. 运行
    client.login()
    
    # 测试单节点 (确保配置了 OpenAI Key 环境变量，或者 mock 成功)
    # client.test_single_node() 
    
    # 测试完整流程
    wf_id = client.create_workflow()
    client.run_workflow_stream(wf_id)