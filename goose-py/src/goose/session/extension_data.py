# goose-py/extension_data.py
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class ExtensionData(BaseModel):
    """
    对应 Rust: ExtensionData
    管理扩展的状态数据，键名为 'extension_name.version' 格式。
    """
    # 使用 flatten 风格，直接存储所有 kv
    extension_states: Dict[str, Any] = Field(default_factory=dict)

    def get_state(self, extension_name: str, version: str = "v0") -> Optional[Any]:
        """获取特定扩展版本的状态"""
        key = f"{extension_name}.{version}"
        return self.extension_states.get(key)

    def set_state(self, extension_name: str, data: Any, version: str = "v0"):
        """设置特定扩展版本的状态"""
        key = f"{extension_name}.{version}"
        self.extension_states[key] = data

    def remove_state(self, extension_name: str, version: str = "v0"):
        key = f"{extension_name}.{version}"
        if key in self.extension_states:
            del self.extension_states[key]