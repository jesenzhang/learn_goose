import sys
import json
import logging

# 配置日志到 stderr，以免污染 stdout (stdout 用于协议通信)
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("mock-server")

def main():
    logger.info("Mock MCP Server Started")
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            request = json.loads(line)
            logger.info(f"Received: {request}")
            
            response = handle_request(request)
            
            if response:
                print(json.dumps(response), flush=True)
                logger.info(f"Sent: {response}")
                
        except Exception as e:
            logger.error(f"Error: {e}")

def handle_request(req):
    method = req.get("method")
    msg_id = req.get("id")
    
    # 1. 握手 (Initialize)
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": { "tools": {} },
                "serverInfo": { "name": "mock-calculator", "version": "1.0" }
            }
        }
    
    # 2. 收到初始化通知 (Initialized Notification)
    elif method == "notifications/initialized":
        return None # 通知不需要回复

    # 3. 列出工具 (Tools List)
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "add_numbers",
                    "description": "Add two numbers together",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "a": { "type": "number", "description": "First number" },
                            "b": { "type": "number", "description": "Second number" }
                        },
                        "required": ["a", "b"]
                    }
                }]
            }
        }

    # 4. 调用工具 (Call Tool)
    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        
        if name == "add_numbers":
            try:
                result = float(args["a"]) + float(args["b"])
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": str(result)
                        }],
                        "isError": False
                    }
                }
            except Exception as e:
                return error_response(msg_id, str(e))
        else:
            return error_response(msg_id, f"Tool not found: {name}")

    # 未知方法
    else:
        # 如果是 request (带 id)，返回错误；如果是 notification，忽略
        if msg_id is not None:
            return error_response(msg_id, "Method not found")
        return None

def error_response(msg_id, message):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": { "code": -32601, "message": message }
    }

if __name__ == "__main__":
    main()