# src/goose/app/auth/service.py
import secrets
import hashlib
import uuid
import time
from typing import Dict
from goose.user.repository import UserRepository
from goose.user.types import UserSession, User
from goose.utils.security import verify_password,create_jwt,create_access_token
from goose.exceptions import AuthError

class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def login(self, username: str, password: str, user_agent: str, ip: str) -> Dict:
        """
        [Login Flow]
        1. 验证密码
        2. 创建 Session 记录 (DB)
        3. 生成 Refresh Token (返回给前端)
        4. 生成 Access Token (返回给前端)
        """
        # 1. 验证用户 (省略密码比对细节)
        user = await self.user_repo.get_by_username(username)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthError("Invalid credentials")

        # 2. 生成 Refresh Token (高熵随机串)
        # 格式建议: <session_id>.<random_secret>
        # 这样前端传回来时，我们可以快速提取 session_id 去查库
        session_id = uuid.uuid4().hex
        random_secret = secrets.token_urlsafe(32)
        refresh_token_raw = f"{session_id}.{random_secret}"
        
        # 计算哈希存库
        rt_hash = hashlib.sha256(refresh_token_raw.encode()).hexdigest()

        # 3. 创建 Session 记录
        session = UserSession(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=rt_hash,
            user_agent=user_agent,
            ip_address=ip,
            expires_at=time.time() + (7 * 24 * 3600) # 7天过期
        )
        await self.user_repo.create_session(session)

        # 4. 生成 JWT Access Token (包含 session_id)
        # Payload: { sub: user_id, sid: session_id, exp: ... }
        access_token = create_jwt(user_id=user.id, session_id=session.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token_raw,
            "token_type": "bearer"
        }

    async def refresh_access_token(self, refresh_token_raw: str) -> str:
        """
        [Refresh Flow] 用 Refresh Token 换取新的 Access Token
        """
        try:
            # 1. 解析 Token: sid.secret
            session_id, secret = refresh_token_raw.split('.')
        except ValueError:
            raise AuthError("Invalid token format")

        # 2. 查库获取 Session
        session = await self.user_repo.get_active_session(session_id)
        if not session:
            raise AuthError("Session expired or revoked")

        # 3. 验证哈希 (确保 Token 没被篡改)
        incoming_hash = hashlib.sha256(refresh_token_raw.encode()).hexdigest()
        if incoming_hash != session.refresh_token_hash:
            # 🚨 严重安全警报：有人试图用伪造的 Token 攻击
            # 策略：立即注销该 Session，甚至封禁用户
            await self.user_repo.revoke_session(session_id)
            raise AuthError("Invalid token")

        # 4. (可选) 刷新 Session 的 last_used_at
        await self.user_repo.touch_session(session_id)

        # 5. 颁发新 JWT
        return create_jwt(user_id=session.user_id, session_id=session.id)