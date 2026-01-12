"""
文博助手示例客户端

用于测试文博助手的对话功能
"""

import asyncio
import json
from typing import Optional
import httpx


class MuseumAssistantClient:
    """文博助手客户端"""

    def __init__(self, base_url: str = "http://localhost:8400"):
        self.base_url = base_url.rstrip('/')
        self.session_id = "demo_session"

    async def send_message(
        self,
        message: str,
        stream: bool = False
    ) -> Optional[str]:
        """发送消息"""
        if stream:
            return await self._send_stream(message)
        else:
            return await self._send_non_stream(message)

    async def _send_stream(self, message: str) -> str:
        """发送流式消息"""
        url = f"{self.base_url}/chat/{self.session_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                url,
                json={"message": message, "stream": True},
                headers={"Accept": "text/event-stream"}
            ) as response:
                if response.status_code != 200:
                    print(f"Error: {response.status_code}")
                    return None

                full_response = ""
                async for chunk in response.aiter_text():
                    if chunk.startswith("data: "):
                        data = chunk[6:]
                        try:
                            event = json.loads(data)
                            if event.get("type") == "token":
                                token = event.get("data", "")
                                print(token, end="", flush=True)
                                full_response += token
                            elif event.get("type") == "error":
                                print(f"\nError: {event.get('data')}")
                                return None
                        except json.JSONDecodeError:
                            pass

                print()
                return full_response

    async def _send_non_stream(self, message: str) -> str:
        """发送非流式消息"""
        url = f"{self.base_url}/chat/{self.session_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json={"message": message, "stream": False}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")
            else:
                print(f"Error: {response.status_code}")
                print(response.text)
                return None

    async def reconnect(self) -> bool:
        """会话重连"""
        url = f"{self.base_url}/chat/{self.session_id}/reconnect"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url)

            if response.status_code == 200:
                print("会话重连成功")
                return True
            else:
                print(f"重连失败: {response.status_code}")
                return False

    async def get_sessions(self) -> list:
        """获取所有会话"""
        url = f"{self.base_url}/sessions"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                return data.get("sessions", [])
            else:
                return []

    async def replay_events(self, since: Optional[str] = None) -> list:
        """事件回放"""
        url = f"{self.base_url}/events/{self.session_id}"
        params = {}
        if since:
            params["since"] = since

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                return data.get("events", [])
            else:
                print(f"Error: {response.status_code}")
                return []


async def demo_basic_chat():
    """基本对话演示"""
    print("=" * 60)
    print("文博助手 - 基本对话演示")
    print("=" * 60)

    client = MuseumAssistantClient()

    questions = [
        "介绍一下唐三彩",
        "现在有什么特展？",
        "明代的历史特点是什么？"
    ]

    for question in questions:
        print(f"\n👤 用户: {question}")
        print("🤖 助手: ", end="", flush=True)
        await client.send_message(question, stream=True)
        print()


async def demo_reconnect():
    """断线重连演示"""
    print("\n" + "=" * 60)
    print("文博助手 - 断线重连演示")
    print("=" * 60)

    client = MuseumAssistantClient()

    print("\n1️⃣ 发送第一条消息")
    print("👤 用户: 记住我喜欢唐三彩")
    print("🤖 助手: ", end="", flush=True)
    await client.send_message("记住我喜欢唐三彩", stream=True)

    print("\n2️⃣ 模拟断线重连")
    await client.reconnect()

    print("\n3️⃣ 发送第二条消息（测试记忆）")
    print("👤 用户: 我喜欢什么？")
    print("🤖 助手: ", end="", flush=True)
    await client.send_message("我喜欢什么？", stream=True)
    print()


async def demo_event_replay():
    """事件回放演示"""
    print("\n" + "=" * 60)
    print("文博助手 - 事件回放演示")
    print("=" * 60)

    client = MuseumAssistantClient()

    print("\n1️⃣ 发送消息产生事件")
    print("👤 用户: 青花瓷有什么特点？")
    print("🤖 助手: ", end="", flush=True)
    await client.send_message("青花瓷有什么特点？", stream=True)

    print("\n2️⃣ 回放事件")
    events = await client.replay_events()

    print(f"\n📊 共回放 {len(events)} 个事件:")
    for i, event in enumerate(events[:5], 1):
        event_type = event.get("type", "unknown")
        print(f"  {i}. {event_type}: {event.get('data', '')[:50]}...")

    if len(events) > 5:
        print(f"  ... 还有 {len(events) - 5} 个事件")

    print()


async def demo_sessions():
    """会话管理演示"""
    print("\n" + "=" * 60)
    print("文博助手 - 会话管理演示")
    print("=" * 60)

    client = MuseumAssistantClient()

    print("\n📋 获取所有会话:")
    sessions = await client.get_sessions()

    if sessions:
        for session in sessions:
            print(f"  • {session.get('id')}: {session.get('title', 'Untitled')}")
    else:
        print("  暂无会话")

    print()


async def main():
    """主函数"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "文博助手客户端演示" + " " * 21 + "║")
    print("╚" + "═" * 58 + "╝")

    try:
        await demo_basic_chat()
        await demo_reconnect()
        await demo_event_replay()
        await demo_sessions()

        print("\n" + "=" * 60)
        print("演示完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
