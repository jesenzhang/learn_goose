"""
实际应用示例 - 如何在实际项目中使用多用户功能

展示从单用户到多用户的平滑迁移
"""

import asyncio
from typing import Optional
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from pydantic import BaseModel

# 假设的导入（实际使用时取消注释）
# from assistant.db import get_db
# from assistant.core.state import AgentState

# ================= 示例 1：API 层 =================

app = FastAPI()
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    stream: bool = False


# ===== 方式 1：单用户模式（原有方式，无需修改）=====

@router.post("/chat/{session_id}")
async def chat_single_user(session_id: str, request: ChatRequest):
    """
    单用户聊天 - 原有方式

    ✅ 无需任何修改
    ✅ 继续使用原有接口
    ✅ 适合单用户应用
    """
    # db = await get_db_async()

    # 原有方式：保存会话
    # state_data = await db.load_state(session_id)
    # if not state_data:
    #     state = AgentState(session_id=session_id, title="新对话")
    # else:
    #     state = AgentState(**state_data)

    # 处理用户输入...

    # 原有方式：保存会话
    # await db.save_state(session_id, state.model_dump())

    return {"status": "success", "message": "单用户模式"}


@router.get("/sessions")
async def list_all_sessions():
    """
    列出所有会话 - 原有方式

    ✅ 返回所有用户的会话
    ✅ 无需任何修改
    """
    # db = await get_db_async()
    # sessions = await db.list_sessions()
    return {"sessions": []}


# ===== 方式 2：多用户模式（新接口）=====

@router.post("/users/{user_id}/chat/{session_id}")
async def chat_multi_user(
    user_id: str,
    session_id: str,
    request: ChatRequest
):
    """
    多用户聊天 - 新接口

    ✅ 用户会话完全隔离
    ✅ 支持用户统计
    ✅ 适合多用户应用
    """
    # db = await get_db_async()

    # 新方式：为指定用户保存会话
    # state_data = await db.load_state_for_user(user_id, session_id)
    # if not state_data:
    #     state = AgentState(
    #         session_id=session_id,
    #         user_id=user_id,  # ← 关键：设置 user_id
    #         title=f"{user_id} 的对话"
    #     )
    # else:
    #     state = AgentState(**state_data)

    # 处理用户输入...

    # 新方式：为指定用户保存会话
    # await db.save_state_for_user(user_id, session_id, state.model_dump())

    return {"status": "success", "message": "多用户模式", "user_id": user_id}


@router.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str, limit: Optional[int] = None):
    """
    列出指定用户的会话

    ✅ 只返回该用户的会话
    ✅ 支持分页
    """
    # db = await get_db_async()
    # sessions = await db.list_sessions_for_user(user_id, limit=limit)
    return {"user_id": user_id, "sessions": []}


@router.get("/users/{user_id}/stats")
async def get_user_statistics(user_id: str):
    """
    获取用户统计信息

    ✅ 会话数、事件数、记忆数
    """
    # db = await get_db_async()
    # stats = await db.get_user_stats(user_id)
    return {"user_id": user_id, "stats": {}}


@router.delete("/users/{user_id}")
async def delete_user_data(user_id: str):
    """
    删除用户数据

    ✅ 删除所有会话、事件、记忆
    """
    # db = await get_db_async()
    # count = await db.delete_user_sessions(user_id)
    return {"user_id": user_id, "deleted": 0}


@router.get("/users")
async def list_all_users():
    """
    列出所有用户

    ✅ 基于会话的用户列表
    """
    # db = await get_db_async()
    # users = await db.list_all_users()
    return {"users": []}


# ===== 方式 3：智能模式（自动检测）=====

@router.post("/chat/{session_id}")
async def chat_smart(
    session_id: str,
    request: ChatRequest,
    user_id: Optional[str] = None
):
    """
    智能聊天 - 自动检测是否需要 user_id

    ✅ 单用户和多用户都支持
    ✅ 向后兼容
    ✅ 灵活切换
    """
    # db = await get_db_async()

    if user_id:
        # 多用户模式
        # state_data = await db.load_state_for_user(user_id, session_id)
        # ...
        # await db.save_state_for_user(user_id, session_id, state.model_dump())
        return {"status": "success", "mode": "multi-user", "user_id": user_id}
    else:
        # 单用户模式（原有逻辑）
        # state_data = await db.load_state(session_id)
        # ...
        # await db.save_state(session_id, state.model_dump())
        return {"status": "success", "mode": "single-user"}


# ================= 示例 2：Agent 层 =================

class AssistantAgent:
    """助手 Agent - 支持多用户"""

    def __init__(self, config_path: str, default_user_id: Optional[str] = None):
        """
        初始化 Agent

        Args:
            config_path: 配置文件路径
            default_user_id: 默认用户 ID（可选）
        """
        self.config_path = config_path
        self.default_user_id = default_user_id
        # self.db = get_db()

    async def run_task(
        self,
        session_id: str,
        user_input: str,
        user_id: Optional[str] = None
    ):
        """
        运行任务（支持 user_id）

        Args:
            session_id: 会话 ID
            user_input: 用户输入
            user_id: 用户 ID（可选，默认使用 default_user_id）
        """
        # 确定有效的 user_id
        effective_user_id = user_id or self.default_user_id

        if effective_user_id:
            # 多用户模式
            # state_data = await self.db.load_state_for_user(effective_user_id, session_id)
            # if not state_data:
            #     state = AgentState(
            #         session_id=session_id,
            #         user_id=effective_user_id,
            #         title=f"{effective_user_id} 的对话"
            #     )
            # else:
            #     state = AgentState(**state_data)

            # ... 处理逻辑 ...

            # 保存
            # await self.db.save_state_for_user(effective_user_id, session_id, state.model_dump())

            return {"user_id": effective_user_id, "mode": "multi-user"}

        else:
            # 单用户模式（原有逻辑）
            # state_data = await self.db.load_state(session_id)
            # if not state_data:
            #     state = AgentState(session_id=session_id)
            # else:
            #     state = AgentState(**state_data)

            # ... 处理逻辑 ...

            # 保存
            # await self.db.save_state(session_id, state.model_dump())

            return {"mode": "single-user"}


# ================= 示例 3：实际应用场景 =================

# ===== 场景 1：个人助手（单用户）=====

class PersonalAssistant:
    """个人助手 - 单用户模式"""

    def __init__(self):
        self.agent = AssistantAgent("config.yaml")

    async def handle_message(self, session_id: str, message: str):
        """
        处理消息（单用户）

        ✅ 无需传递 user_id
        ✅ 使用原有接口
        """
        # 单用户模式
        # result = await self.agent.run_task(session_id, message)
        return result


# ===== 场景 2：Web 应用（多用户）=====

class WebAssistant:
    """Web 应用助手 - 多用户模式"""

    def __init__(self):
        self.agent = AssistantAgent("config.yaml", default_user_id="guest")

    async def handle_message(
        self,
        user_id: str,
        session_id: str,
        message: str
    ):
        """
        处理消息（多用户）

        ✅ 需要传递 user_id
        ✅ 使用多用户接口
        """
        # 多用户模式
        # result = await self.agent.run_task(session_id, message, user_id=user_id)
        return result


# ===== 场景 3：混合应用（逐步迁移）=====

class HybridAssistant:
    """混合助手 - 支持单用户和多用户"""

    def __init__(self):
        self.agent = AssistantAgent("config.yaml")

    async def handle_message(
        self,
        user_id: Optional[str],
        session_id: str,
        message: str
    ):
        """
        处理消息（智能模式）

        ✅ 根据 user_id 自动选择模式
        ✅ 向后兼容
        """
        # 智能模式
        # result = await self.agent.run_task(session_id, message, user_id=user_id)
        return result


# ================= 示例 4：Session ID 管理 =================

import time
import uuid


def generate_session_id(user_id: str) -> str:
    """
    生成会话 ID（推荐格式）

    格式：{user_id}_{timestamp}_{random}

    Args:
        user_id: 用户 ID

    Returns:
        会话 ID
    """
    return f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def extract_user_id(session_id: str) -> Optional[str]:
    """
    从 session_id 提取用户 ID

    Args:
        session_id: 会话 ID

    Returns:
        用户 ID，如果格式不匹配则返回 None
    """
    if '_' not in session_id:
        return None
    return session_id.split('_')[0]


# 使用示例
user_id = "alice"
session_id = generate_session_id(user_id)
# 结果：alice_1704096000_abc12345

# 提取用户
extracted_user = extract_user_id(session_id)
# 结果：alice


# ================= 示例 5：错误处理和权限检查 =================

class SecureAssistant:
    """安全助手 - 带权限检查"""

    def __init__(self):
        self.agent = AssistantAgent("config.yaml")

    async def handle_message(
        self,
        current_user_id: str,
        session_id: str,
        message: str
    ):
        """
        处理消息（带权限检查）

        ✅ 自动检查用户权限
        ✅ 防止越权访问
        """
        # 提取会话所属的用户
        session_owner = extract_user_id(session_id)

        if session_owner:
            # 会话属于特定用户
            if session_owner != current_user_id:
                # 权限检查失败
                raise HTTPException(
                    status_code=403,
                    detail=f"无权访问用户 {session_owner} 的会话"
                )

            # 多用户模式
            # result = await self.agent.run_task(
            #     session_id,
            #     message,
            #     user_id=current_user_id
            # )
            return {"mode": "multi-user", "authorized": True}

        else:
            # 会话不特定于用户（旧会话）
            # 使用默认用户或允许访问
            # result = await self.agent.run_task(
            #     session_id,
            #     message,
            #     user_id=current_user_id
            # )
            return {"mode": "legacy", "authorized": True}


# ================= 使用示例 =================

async def main():
    """主函数 - 演示各种使用方式"""

    print("\n" + "=" * 60)
    print("实际应用示例")
    print("=" * 60)

    # ===== 示例 1：个人助手 =====
    print("\n示例 1：个人助手（单用户）")
    personal = PersonalAssistant()
    # await personal.handle_message("session_001", "你好")
    print("✅ 单用户模式 - 无需 user_id")

    # ===== 示例 2：Web 应用 =====
    print("\n示例 2：Web 应用（多用户）")
    web = WebAssistant()
    # await web.handle_message("alice", "alice_session_001", "你好")
    # await web.handle_message("bob", "bob_session_001", "你好")
    print("✅ 多用户模式 - 需要 user_id")

    # ===== 示例 3：混合应用 =====
    print("\n示例 3：混合应用（智能模式）")
    hybrid = HybridAssistant()
    # 无 user_id - 单用户模式
    # await hybrid.handle_message(None, "session_001", "你好")
    # 有 user_id - 多用户模式
    # await hybrid.handle_message("alice", "alice_session_001", "你好")
    print("✅ 智能模式 - 自动检测")

    # ===== 示例 4：权限检查 =====
    print("\n示例 4：权限检查")
    secure = SecureAssistant()
    try:
        # Alice 尝试访问 Alice 的会话
        # await secure.handle_message("alice", "alice_session_001", "你好")
        print("✅ 权限检查通过")
    except HTTPException as e:
        print(f"❌ 权限检查失败: {e.detail}")

    # ===== 示例 5：会话管理 =====
    print("\n示例 5：会话管理")

    user_id = "alice"
    sessions = []
    for i in range(3):
        session_id = generate_session_id(user_id)
        sessions.append(session_id)
        print(f"  会话 {i+1}: {session_id}")

    print(f"\n生成了 {len(sessions)} 个会话")

    # 提取用户
    for session_id in sessions[:2]:
        owner = extract_user_id(session_id)
        print(f"  {session_id} 属于: {owner}")

    print("\n" + "=" * 60)


# ================= 迁移指南 =================

class MigrationGuide:
    """迁移指南 - 从单用户到多用户"""

    @staticmethod
    def phase1_single_user():
        """阶段 1：保持单用户模式"""
        print("阶段 1：继续使用单用户模式")
        print("  - 原有代码无需修改")
        print("  - 使用原有接口")
        print("  - 适合：个人助手")

    @staticmethod
    def phase2_add_user_id():
        """阶段 2：添加 user_id 支持"""
        print("阶段 2：添加 user_id 参数")
        print("  - 在函数签名中添加 user_id 参数")
        print("  - 使用新接口 save_state_for_user 等")
        print("  - 适合：需要用户隔离")

    @staticmethod
    def phase3_smart_mode():
        """阶段 3：启用智能模式"""
        print("阶段 3：启用智能模式")
        print("  - 自动检测是否需要 user_id")
        print("  - 保持向后兼容")
        print("  - 适合：平滑迁移")

    @staticmethod
    def phase4_full_migration():
        """阶段 4：完全迁移"""
        print("阶段 4：完全迁移到多用户")
        print("  - 所有功能使用多用户接口")
        print("  - 完全启用用户隔离")
        print("  - 适合：SaaS 应用")

    @staticmethod
    def show_roadmap():
        """显示迁移路线图"""
        print("\n" + "=" * 60)
        print("迁移路线图")
        print("=" * 60)

        MigrationGuide.phase1_single_user()
        MigrationGuide.phase2_add_user_id()
        MigrationGuide.phase3_smart_mode()
        MigrationGuide.phase4_full_migration()

        print("\n" + "=" * 60)


if __name__ == "__main__":
    # 运行示例
    # asyncio.run(main())

    # 显示迁移路线图
    MigrationGuide.show_roadmap()
