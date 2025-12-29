from typing import Dict, Any
from .openai import OpenAIProvider
from .factory import ProviderFactory

@ProviderFactory.register("siliconflow")
class SiliconFlowProvider(OpenAIProvider):
    """
    SiliconFlow (硅基流动) Provider
    本质上是 OpenAI 协议，但有特定的默认 Base URL
    """
    def __init__(self, model_config: Dict[str, Any]):
        # 强制设置 Base URL，除非用户显式覆盖
        if "base_url" not in model_config:
            model_config["base_url"] = "https://api.siliconflow.cn/v1"
            
        super().__init__(model_config)