# goose-py/extension_data.py
from typing import Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

# src/goose/session/extension_data.py

from typing import Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

class ExtensionData(BaseModel):
    """
    专门用于存储扩展/插件的状态数据。
    核心作用是提供命名空间隔离，防止不同插件的数据冲突。
    """
    # 底层存储：Key 是 Extension 的名字，Value 是它的状态字典
    data: Dict[str, Any] = Field(default_factory=dict)

    def get(self, ext_name: str, default: Any = None) -> Any:
        return self.data.get(ext_name, default)

    def set(self, ext_name: str, value: Any):
        self.data[ext_name] = value

    def get_as_model(self, ext_name: str, model_cls: Type[T]) -> Optional[T]:
        """
        高级功能：尝试将存储的字典转换为具体的 Pydantic 模型
        """
        raw = self.data.get(ext_name)
        if raw is None:
            return None
        return model_cls.model_validate(raw)