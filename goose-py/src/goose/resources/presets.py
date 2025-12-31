from typing import List
from goose.config import SystemConfig # 引入类型
from goose.resources.types import ResourceMetadata, ResourceKind, ResourceScope

# [修改] 接收 config 参数
def get_system_presets(config: SystemConfig) -> List[ResourceMetadata]:
    resources = []

    resources.append(ResourceMetadata(
        id="qwen3_vl",
        kind=ResourceKind.LLM,
        scope=ResourceScope.SYSTEM,
        provider="openai",
        config={
            "model_name": "qwen3_vl",
            "api_key": config.openai_api_key, 
            "base_url": 'http://192.168.10.180:8088/v1/',
        }
    ))
    
    resources.append(ResourceMetadata(
        id="Qwen/Qwen2.5-7B",
        kind=ResourceKind.LLM,
        scope=ResourceScope.SYSTEM,
        provider="openai",
        config={
            "model_name": "Qwen/Qwen2.5-7B-Instruct",
            "api_key": config.silicon_api_key, 
            "base_url": config.silicon_base_url,
        }
    ))

    resources.append(ResourceMetadata(
        id="sys.tool.google_search",
        kind=ResourceKind.TOOL,
        scope=ResourceScope.SYSTEM,
        provider="serpapi",
        config={
            "api_key": config.serpapi_api_key
        }
    ))

    return resources