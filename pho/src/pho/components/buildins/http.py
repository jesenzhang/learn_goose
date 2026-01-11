import httpx
import json
from typing import Dict, Any, Literal, Union, Optional
from pydantic import BaseModel, Field

from pho.components.base import Component
from pho.utils.template import TemplateRenderer # 使用 Goose 的渲染器
from pho.components.registry import register_component
from pho.types import NodeTypes

class HttpConfig(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field("GET", description="HTTP方法")
    url: str = Field(..., description="请求URL (支持 {{var}} 模板)")
    headers: Dict[str, str] = Field(default_factory=dict, description="请求头")
    
    # Body 类型
    body_type: Literal["json", "form-data", "x-www-form-urlencoded", "raw", "none"] = Field("none", alias="bodyType")
    
    # Body 内容
    body: Union[str, Dict[str, Any], None] = Field(None)
    
    timeout: int = Field(10, description="超时时间(秒)")

@register_component(
    name=NodeTypes.HTTP_REQUESTER,
    group="Utilities",
    label="HTTP 请求",
    description="发送自定义 HTTP 请求",
    icon="globe",
    author="System",
    version="1.0.0",
    config_model=HttpConfig
)
class HttpRequester(Component):
    async def execute(self, inputs: Dict[str, Any], config: HttpConfig) -> Dict[str, Any]:
        # 1. 渲染 URL
        url = TemplateRenderer.render(config.url, inputs)
        
        # 2. 渲染 Headers
        headers = {}
        for k, v in config.headers.items():
            headers[k] = TemplateRenderer.render(v, inputs)
            
        # 3. 处理 Body
        json_data = None
        data_data = None
        content_data = None
        
        if config.method not in ["GET", "HEAD"] and config.body_type != "none":
            raw_body = config.body
            
            # 如果 body 是字符串模板，先渲染
            rendered_body = raw_body
            if isinstance(raw_body, str):
                rendered_body = TemplateRenderer.render(raw_body, inputs)
            # 如果是 dict，通常用于 form，这里简化处理，暂不递归渲染 dict values
            
            if config.body_type == "json":
                # JSON 处理
                if isinstance(rendered_body, str):
                    try:
                        json_data = json.loads(rendered_body)
                    except json.JSONDecodeError:
                        # 解析失败，作为 raw 发送但带 json header
                        content_data = rendered_body
                        if "Content-Type" not in headers:
                            headers["Content-Type"] = "application/json"
                else:
                    json_data = rendered_body

            elif config.body_type == "x-www-form-urlencoded":
                data_data = rendered_body
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
            
            elif config.body_type == "raw":
                content_data = rendered_body
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "text/plain"

        # 4. 发送请求
        print(f" 🌍 HTTP {config.method} {url}")
        
        async with httpx.AsyncClient(timeout=config.timeout, follow_redirects=True) as client:
            try:
                resp = await client.request(
                    method=config.method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    data=data_data,
                    content=content_data
                )
                
                # 5. 构造响应
                body_result = resp.text
                try:
                    body_result = resp.json()
                except:
                    pass
                
                return {
                    "status_code": resp.status_code,
                    "status": resp.status_code,
                    "body": body_result,
                    "headers": dict(resp.headers),
                    "is_success": resp.is_success
                }
                
            except Exception as e:
                raise RuntimeError(f"HTTP Request Failed: {str(e)}")