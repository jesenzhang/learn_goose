# src/goose/server/security.py
import jwt
import time
from typing import Optional, Dict
from passlib.context import CryptContext

from goose.system_config import get_config

# --- 1. 密码哈希工具 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与数据库中的哈希匹配
    """
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    生成密码哈希 (注册时用)
    """
    return pwd_context.hash(password)

# --- 2. JWT 工具 ---
def create_jwt(user_id: str, session_id: str,secret_key:str=None,algorithm:str=None,expire_time:int=None) -> str:
    """
    生成 Access Token (JWT)
    Payload 包含:
      - sub: 用户ID (Subject)
      - sid: 会话ID (Session ID, 用于关联 user_sessions 表)
      - exp: 过期时间
    """
    expire = time.time() + (expire_time * 60)
    
    to_encode = {
        "sub": user_id,
        "sid": session_id,  # [关键] 将 Session ID 写入 Token
        "exp": expire,
        "iat": time.time()  # 签发时间
    }
    secret_key = secret_key or get_config().jwt_secret_key
    algorithm = algorithm or get_config().jwt_algorithm
    expire_time = expire_time or get_config().jwt_expire_minutes
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    return encoded_jwt

def create_access_token(data: Dict, secret_key:str =None, algorithm:str =None, expire_minutes: int = None, expires_delta: int = None) -> str:
    """生成 JWT Token"""
    to_encode = data.copy()
    secret_key = secret_key or get_config().jwt_secret_key
    algorithm = algorithm or get_config().jwt_algorithm
    expire_time = expire_minutes or get_config().jwt_expire_minutes
    
    if expires_delta:
        expire = time.time() + (expires_delta * 60)
    else:
        expire = time.time() + (expire_time * 60)
        
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        secret_key, 
        algorithm=algorithm
    )
    return encoded_jwt

def decode_access_token(token: str, secret_key:str, algorithm:str = None) -> Optional[str]:
    """
    解析 Token 并返回 user_id (sub)
    如果无效或过期，返回 None
    """
    try:
        secret_key = secret_key or get_config().jwt_secret_key
        algorithm = algorithm or get_config().jwt_algorithm
        
        payload = jwt.decode(
            token, 
            secret_key, 
            algorithms=[algorithm]
        )
        user_id: str = payload.get("sub")
        # 还可以校验 "exp" 但 pyjwt 默认会校验
        return user_id
    except jwt.PyJWTError:
        return None