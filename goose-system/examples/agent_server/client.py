"""
Goose Agent Client Example

完整的 Agent 客户端示例，包括：
- 用户注册/登录/登出
- 会话管理
- 消息发送和接收
- 工具调用

运行：
    python client.py

使用：
    # 注册用户
    python client.py register alice password123 alice@example.com

    # 登录
    python client.py login alice password123

    # 发送消息
    python client.py chat --session-id <session_id> "Hello, world!"

    # 查看会话列表
    python client.py list-sessions
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("aiohttp not installed. Install with: pip install aiohttp")

# 配置
API_BASE_URL = "http://127.0.0.1:8080"
API_VERSION = "v1"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("goose.client.example")


class GooseClient:
    """
    Goose Agent Client

    功能：
    - 用户认证（注册/登录/登出）
    - 会话管理
    - 消息发送和接收
    - 工具调用
    """

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        api_version: str = API_VERSION,
    ):
        """
        初始化客户端

        Args:
            base_url: 服务器基础 URL
            api_version: API 版本
        """
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.session_id: Optional[str] = None
        self.user_info: Optional[Dict[str, Any]] = None
        self._client: Optional[aiohttp.ClientSession] = None

    def _api_url(self, endpoint: str) -> str:
        """构建 API URL"""
        return f"{self.base_url}/api/{self.api_version}/{endpoint}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """HTTP 请求封装"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not available")

        url = self._api_url(endpoint)
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        # 添加会话 ID 头
        if self.session_id:
            request_headers["X-Session-ID"] = self.session_id

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=url,
                headers=request_headers,
                json=data,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Request failed: {response.status} - {error_text}")
                    return {
                        "error": error_text,
                        "status": response.status,
                    }

                response_text = await response.text()
                return json.loads(response_text) if response_text else {}

    async def register_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        role: str = "user",
    ) -> Dict[str, Any]:
        """注册用户"""
        data = {
            "username": username,
            "password": password,
        }
        if email:
            data["email"] = email
        if role:
            data["role"] = role

        logger.info(f"Registering user: {username}")
        return await self._request("POST", "auth/register", data=data)

    async def login_user(
        self,
        username: str,
        password: str,
        expire_hours: int = 24,
    ) -> Dict[str, Any]:
        """用户登录"""
        data = {
            "username": username,
            "password": password,
            "expire_hours": expire_hours,
        }

        logger.info(f"Logging in user: {username}")
        result = await self._request("POST", "auth/login", data=data)

        if result.get("success") and result.get("session_id"):
            self.session_id = result["session_id"]
            self.user_info = result.get("user")
            logger.info(f"Login successful, session: {self.session_id}")

        return result

    async def logout_user(self) -> Dict[str, Any]:
        """用户登出"""
        if not self.session_id:
            return {"error": "No active session"}

        data = {"session_id": self.session_id}

        logger.info(f"Logging out from session: {self.session_id}")
        result = await self._request("POST", "auth/logout", data=data)

        if result.get("success"):
            self.session_id = None
            self.user_info = None

        return result

    async def get_profile(self) -> Dict[str, Any]:
        """获取用户信息"""
        if not self.session_id:
            return {"error": "No active session"}

        logger.info("Fetching user profile")
        return await self._request("GET", f"auth/profile?session_id={self.session_id}")

    async def list_sessions(self) -> Dict[str, Any]:
        """列出所有会话"""
        logger.info("Listing sessions")
        return await self._request("GET", "sessions")

    async def create_session(self, working_dir: str, name: Optional[str] = None) -> Dict[str, Any]:
        """创建新会话"""
        data = {
            "working_dir": working_dir,
            "name": name or "New Session",
        }

        logger.info(f"Creating session with working dir: {working_dir}")
        result = await self._request("POST", "sessions", data=data)

        if result.get("session_id"):
            self.session_id = result["[session_id]"]

        return result

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取会话信息"""
        logger.info(f"Fetching session: {session_id}")
        return await self._request("GET", f"sessions/{session_id}")

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """删除会话"""
        logger.info(f"Deleting session: {session_id}")
        return await self._request("DELETE", f"sessions/{session_id}")

    async def send_message(
        self,
        message: str,
        role: str = "user",
    ) -> Dict[str, Any]:
        """发送消息（占位，需要实际的 agent 实现）"""
        logger.info(f"Sending message as {role}: {message[:50]}...")
        return {
            "status": "message_sent",
            "message": message,
            "role": role,
        }

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """调用工具"""
        data = {
            "session_id": self.session_id,
            "name": tool_name,
            "arguments": arguments,
        }

        logger.info(f"Calling tool: {tool_name} with args: {arguments}")
        return await self._request("POST", "agent/call_tool", data=data)

    async def get_tools(self, extension_name: Optional[str] = None) -> Dict[str, Any]:
        """获取可用工具"""
        if not self.session_id:
            return {"error": "No active session"}

        endpoint = f"agent/tools?session_id={self.session_id}"
        if extension_name:
            endpoint += f"&extension_name={extension_name}"

        logger.info("Fetching available tools")
        return await self._request("GET", endpoint)

    async def start_agent(
        self,
        working_dir: str,
        recipe_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        启动 agent

        创建新会话并启动 agent 实例
        """
        data = {
            "working_dir": working_dir,
            "recipe_id": recipe_id,
        }

        logger.info(f"Starting agent in: {working_dir}")
        result = await self._request("POST", "agent/start", data=data)

        if result.get("session_id"):
            self.session_id = result["session_id"]

        return result

    async def stop_agent(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        停止 agent

        停止 agent 实例
        """
        sid = session_id or self.session_id

        if not sid:
            return {"error": "No session specified"}

        data = {"session_id": sid}

        logger.info(f"Stopping agent: {sid}")
        return await self._request("POST", "agent/stop", data=data)

    # 便捷方法

    async def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.session_id is not None and self.user_info is not None

    def get_session_info(self) -> Dict[str, Any]:
        """获取当前会话信息"""
        return {
            "session_id": self.session_id,
            "user_info": self.user_info,
            "authenticated": self.session_id is not None,
        }


# CLI 命令处理


async def command_register(client: GooseClient, username: str, password: str, email: Optional[str] = None, role: Optional[str] = None):
    """注册命令"""
    result = await client.register_user(username, password, email, role or "user")

    if "error" in result:
        print(f"❌ Registration failed: {result['error']}")
        return

    print(f"✅ User registered successfully!")
    print(f"   Username: {result['username']}")
    print(f"   User ID: {result['user_id']}")
    if result.get("email"):
        print(f"   Email: {result['email']}")


async def command_login(client: GooseClient, username: str, password: str):
    """登录命令"""
    result = await client.login_user(username, password)

    if "error" in result:
        print(f"❌ Login failed: {result['error']}")
        return

    print(f"✅ Login successful!")
    print(f"   Session ID: {result['session_id']}")
    print(f"   User: {result['user']['username']}")
    print(f"   Role: {result['user']['role']}")

    # 显示会话信息
    if result.get("session_id"):
        client.session_id = result["session_id"]
        print("\n💡 Use --session-id to send messages in future commands")


async def command_logout(client: GooseClient):
    """登出命令"""
    result = await client.logout_user()

    if "error" in result:
        print(f"❌ Logout failed: {result['error']}")
        return

    print("✅ Logged out successfully!")


async def command_profile(client: GooseClient):
    """获取配置文件命令"""
    result = await client.get_profile()

    if "error" in result:
        print(f"❌ Failed to get profile: {result['error']}")
        return

    print(f"✅ User Profile:")
    print(f"   User ID: {result['user_id']}")
    print(f"   Username: {result['username']}")
    print(f"   Email: {result.get('email', 'N/A')}")
    print(f"   Role: {result['role']}")
    print(f"   Created: {result['created_at']}")
    print(f"   Active: {result['is_active']}")


async def command_sessions(client: GooseClient):
    """列出会话命令"""
    result = await client.list_sessions()

    if "error" in result:
        print(f"❌ Failed to list sessions: {result['error']}")
        return

    sessions = result.get("sessions", [])
    print(f"✅ Found {len(sessions)} sessions:")

    for i, session in enumerate(sessions[:10], 1):
        name = session.get("name", session.get("session_id", "unknown"))
        sid = session.get("session_id", "unknown")
        created = session.get("created_at", "unknown")
        print(f"   {i}. {name}")
        print(f"      ID: {sid}")
        print(f"      Created: {created}")

    if len(sessions) > 10:
        print(f"\n   ... and {len(sessions) - 10} more sessions")


async def command_create_session(client: GooseClient, working_dir: str, name: Optional[str] = None):
    """创建会话命令"""
    result = await client.create_session(working_dir, name)

    if "error" in result:
        print(f"❌ Failed to create session: {result['error']}")
        return

    print(f"✅ Session created successfully!")
    print(f"   Session ID: {result['session_id']}")
    print(f"   Name: {result['name']}")
    print(f"   Working dir: {working_dir}")

    client.session_id = result["[session_id]"]


async def command_chat(client: GooseClient, message: str):
    """发送消息命令"""
    if not client.session_id:
        print("❌ No active session. Use --session-id to specify a session.")
        return

    result = await client.send_message(message)

    if "error" in result:
        print(f"❌ Failed to send message: {result['error']}")
        return

    print(f"✅ Message sent: {result['message'][:50]}...")


async def command_start_agent(client: GooseClient, working_dir: str):
    """启动 agent 命令"""
    result = await client.start_agent(working_dir)

    if "error" in result:
        print(f"❌ Failed to start agent: {result['error']}")
        return

    print(f"✅ Agent started successfully!")
    print(f"   Session ID: {result.get('session_id', 'unknown')}")

    if result.get("session_id"):
        client.session_id = result["session_id"]


async def command_tools(client: GooseClient, extension: Optional[str] = None):
    """获取工具命令"""
    result = await client.get_tools(extension)

    if "error" in result:
        print(f"❌ Failed to get tools: {result['error']}")
        return

    tools = result if isinstance(result, list) else result.get("tools", [])
    print(f"✅ Available tools ({len(tools)}):")

    for tool in tools:
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")
        print(f"   - {name}")
        if desc:
            print(f"     {desc}")


async def command_call_tool(client: GooseClient, tool_name: str, args_json: str):
    """调用工具命令"""
    try:
        arguments = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON for arguments: {e}")
        return

    result = await client.call_tool(tool_name, arguments)

    if "error" in result:
        print(f"❌ Failed to call tool: {result['error']}")
        return

    print(f"✅ Tool called: {tool_name}")
    print(f"   Arguments: {json.dumps(arguments, indent=2)}")
    print(f"   Result: {json.dumps(result.get('result', 'N/A'), indent=2)}")


def print_help():
    """打印帮助信息"""
    print("""
Goose Agent Client

Usage: python client.py <command> [options]

Commands:
    register <username> <password> [--email <email>] [--role <role>]
        Register a new user

    login <username> <password>
        Login as user and create a session

    logout
        Logout from current session

    profile
        Get current user profile

    sessions
        List all sessions

    create-session <working_dir> [--name <name>]
        Create a new session

    chat <message>
        Send a message to current session

    start-agent <working_dir>
        Start an agent with a given working directory

    tools [--extension <name>]
        List available tools

    call-tool <tool_name> <arguments_json>
        Call a tool with JSON arguments

Options:
    --session-id <id>
        Set the active session ID

    --base-url <url>
        API base URL (default: http://127.0.0.1:8080)

Examples:
    # Register and login
    python client.py register alice password123 --email alice@example.com
    python client.py login alice password123

    # Create session and chat
    python client.py create-session ./workspace --name "My Project"
    python client.py chat "Hello, Goose!"

    # Start agent
    python client.py start-agent ./my-project

    # List tools
    python client.py tools

    # Call tool
    python client.py call-tool read_file '{"path": "example.txt"}'
    """)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Goose Agent Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 全局选项
    parser.add_argument("--base-url", type=str, default=API_BASE_URL, help="API base URL")
    parser.add_argument("--session-id", type=str, help="Active session ID")

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # register 命令
    register_parser = subparsers.add_parser("register", help="Register a new user")
    register_parser.add_argument("username", type=str, help="Username")
    register_parser.add_argument("password", type=str, help="Password")
    register_parser.add_argument("--email", type=str, help="Email address")
    register_parser.add_argument("--role", type=str, default="user", help="User role")

    # login 命令
    login_parser = subparsers.add_parser("login", help="Login as user")
    login_parser.add_argument("username", type=str, help="Username")
    login_parser.add_argument("password", type=str, help="Password")

    # logout 命令
    subparsers.add_parser("logout", help="Logout from current session")

    # profile 命令
    subparsers.add_parser("profile", help="Get user profile")

    # sessions 命令
    subparsers.add_parser("sessions", help="List all sessions")

    # create-session 命令
    create_session_parser = subparsers.add_parser("create-session", help="Create a new session")
    create_session_parser.add_argument("working_dir", type=str, help="Working directory")
    create_session_parser.add_argument("--name", type=str, help="Session name")

    # chat 命令
    chat_parser = subparsers.add_parser("chat", help="Send a message")
    chat_parser.add_argument("message", type=str, help="Message to send")

    # start-agent 命令
    start_parser = subparsers.add_parser("start-agent", help="Start an agent")
    start_parser.add_argument("working_dir", type=str, help="Working directory")

    # tools 命令
    tools_parser = subparsers.add_parser("tools", help="List available tools")
    tools_parser.add_argument("--extension", type=str, help="Filter by extension name")

    # call-tool 命令
    call_tool_parser = subparsers.add_parser("call-tool", help="Call a tool")
    call_tool_parser.add_argument("tool_name", type=str, help="Tool name")
    call_tool_parser.add_argument("arguments_json", type=str, help="Arguments as JSON string")

    args = parser.parse_args()

    if args.command is None:
        print_help()
        return

    # 创建客户端
    client = GooseClient(base_url=args.base_url)

    # 设置会话 ID（如果指定）
    if args.session_id:
        client.session_id = args.session_id
        logger.info(f"Using session: {args.session_id}")

    # 执行命令
    if args.command == "register":
        await command_register(
            client, args.username, args.password,
            args.email, args.role,
        )

    elif args.command == "login":
        await command_login(client, args.username, args.password)

    elif args.command == "logout":
        await command_logout(client)

    elif args.command == "profile":
        await command_profile(client)

    elif args.command == "sessions":
        await command_sessions(client)

    elif args.command == "create-session":
        await command_create_session(client, args.working_dir, args.name)

    elif args.command == "chat":
        await command_chat(client, args.message)

    elif args.command == "start-agent":
        await command_start_agent(client, args.working_dir)

    elif args.command == "tools":
        await command_tools(client, args.extension)

    elif args.command == "call-tool":
        await command_call_tool(client, args.tool_name, args.arguments_json)

    else:
        print_help()


if __name__ == "__main__":
    asyncio.run(main())
