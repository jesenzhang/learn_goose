from typing import TypeVar, Generic, Dict, Type, Awaitable, Any
from abc import ABC, abstractmethod

# 定义泛型 R (Result)，表示命令执行后的返回值类型
R = TypeVar("R")

class Command(ABC, Generic[R]):
    """所有命令的基类，携带返回值类型信息"""
    pass

class ICommandHandler(ABC, Generic[R]):
    """处理者的接口"""
    @abstractmethod
    async def handle(self, command: Command[R]) -> R:
        pass

class CommandBus:
    """命令总线：负责注册 Handler 和分发 Command"""
    def __init__(self):
        # 注册表：Command类型 -> Handler实例
        self._handlers: Dict[Type[Command], ICommandHandler] = {}

    def register(self, command_type: Type[Command], handler: ICommandHandler):
        """注册命令与其处理者"""
        self._handlers[command_type] = handler

    async def send(self, command: Command[R]) -> R:
        """发送命令并等待结果"""
        command_type = type(command)
        handler = self._handlers.get(command_type)
        
        if not handler:
            raise ValueError(f"No handler registered for {command_type.__name__}")
        
        return await handler.handle(command)