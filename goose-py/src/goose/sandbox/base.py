from abc import ABC, abstractmethod
from typing import Dict,Any

class ICodeSandbox(ABC):
    """代码沙箱抽象基类"""
    
    @abstractmethod
    async def run_code(self, code: str, inputs: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        """
        运行代码并返回结果字典。
        必须保证:
        1. 代码中的 'main' 函数被调用。
        2. inputs 作为参数传入 main。
        3. 返回值必须是 Dict (或被包装为 Dict)。
        """
        pass
