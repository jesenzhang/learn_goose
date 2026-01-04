# src/goose/server/security.py
import jwt
import time
from typing import Optional, Dict

def create_access_token(data: Dict, jwt_secret_key:str, jwt_algorithm = "HS256", jwt_expire_minutes: int = 15, expires_delta: int = None) -> str:
    """生成 JWT Token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = time.time() + (expires_delta * 60)
    else:
        expire = time.time() + (jwt_expire_minutes * 60)
        
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        jwt_secret_key, 
        algorithm=jwt_algorithm
    )
    return encoded_jwt

def decode_access_token(token: str,jwt_secret_key:str,jwt_algorithm= "HS256") -> Optional[str]:
    """
    解析 Token 并返回 user_id (sub)
    如果无效或过期，返回 None
    """
    try:
        payload = jwt.decode(
            token, 
            jwt_secret_key, 
            algorithms=[jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        # 还可以校验 "exp" 但 pyjwt 默认会校验
        return user_id
    except jwt.PyJWTError:
        return None