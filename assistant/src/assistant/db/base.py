"""
数据库抽象基类

定义数据库接口， RemoteDatabaseManager 和 AsyncDatabaseManager 都实现此基类

职责：
- 定义统一的数据库接口
- 提供公共的辅助方法
- 不包含具体实现细节
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class DatabaseBase(ABC):
    """
    数据库抽象基类
    
    定义统一的数据库接口，所有数据库实现都必须继承此类
    """

    @abstractmethod
    async def initialize(self):
        """初始化数据库连接和表结构"""
        pass

    @abstractmethod
    async def close(self):
        """关闭数据库连接"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass

    # ================= Session Operations =================
    
    @abstractmethod
    async def create_session(self, title: str = "New Chat") -> Optional[int]:
        """创建新会话"""
        pass

    @abstractmethod
    async def save_state(self, session_id: int, state: Dict[str, Any]) -> bool:
        """保存会话状态"""
        pass

    @abstractmethod
    async def load_state(self, session_id: int) -> Optional[Dict[str, Any]]:
        """加载会话状态"""
        pass

    @abstractmethod
    async def delete_state(self, session_id: int) -> bool:
        """删除会话状态"""
        pass

    @abstractmethod
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        pass

    # ================= Message Operations =================
    
    @abstractmethod
    async def add_message(self, session_id: int, role: str, content: str,
                        metadata: Optional[Dict] = None, **kwargs) -> bool:
        """添加消息到 messages 表"""
        pass

    @abstractmethod
    async def get_messages(self, session_id: int) -> List[Dict[str, Any]]:
        """获取会话的所有消息"""
        pass

    # ================= Event Operations =================
    
    @abstractmethod
    async def save_event(self, session_id: int, event: Dict[str, Any]) -> bool:
        """保存事件"""
        pass

    @abstractmethod
    async def load_events(self, session_id: int) -> List[Dict[str, Any]]:
        """加载事件"""
        pass

    @abstractmethod
    async def delete_events(self, session_id: int) -> bool:
        """删除事件"""
        pass

    # ================= Multi-User Operations =================
    
    @abstractmethod
    async def save_state_for_user(self, user_id: int, session_id: int, state: Dict[str, Any]) -> bool:
        """为指定用户保存会话状态"""
        pass

    @abstractmethod
    async def load_state_for_user(self, user_id: int, session_id: int) -> Optional[Dict[str, Any]]:
        """加载指定用户的会话状态"""
        pass

    @abstractmethod
    async def list_sessions_for_user(self, user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """列出用户的所有会话"""
        pass

    @abstractmethod
    async def delete_user_sessions(self, user_id: int) -> int:
        """删除用户的所有会话"""
        pass

    # ================= Utility Methods =================
    
    async def get_db_info(self) -> Dict[str, Any]:
        """获取数据库信息"""
        return {
            "type": self.__class__.__name__,
            "initialized": True
        }

    async def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        return await self.get_db_info()
