import os
import json
import time
from typing import List, Tuple, Any, AsyncGenerator, Optional, Dict
from openai import AsyncOpenAI

from goose.conversation import (
    Message, Role, 
    TextContent, ImageContent, 
    ToolRequest, ToolResponse, # 使用正确的类名
    ToolCallResult, CallToolRequestParam # 引入必要的泛型结构
)
from goose.model import ModelConfig
from .base import Provider, ProviderUsage, Usage
from .usage_estimator import ensure_usage_tokens

class OpenAIProvider(Provider):
    def __init__(
        self, 
        model_config: ModelConfig, 
        api_key: Optional[str] = None, 
        base_url: Optional[str] = None
    ):
        self.model_config = model_config
        
        # 1. 确定 API Key
        final_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not final_api_key:
            final_api_key = "EMPTY" 
            
        # 2. 确定 Base URL
        final_base_url = base_url or os.getenv("OPENAI_BASE_URL")

        # 初始化客户端
        self.client = AsyncOpenAI(
            api_key=final_api_key, 
            base_url=final_base_url.rstrip("/") if final_base_url else None
        )

    def get_model_config(self) -> ModelConfig:
        return self.model_config

    def _prepare_messages(self, system: str, messages: List[Message]) -> List[dict]:
        """
        将 Goose Message 转换为 OpenAI 格式。
        策略：包含图片的用 List[Dict]，纯文本的用 String (兼容 vLLM/Qwen)。
        """
        openai_msgs = []
        
        # 1. System Prompt
        if system:
            role = "developer" if self.model_config.model_name.startswith("o") else "system"
            openai_msgs.append({"role": role, "content": system})

        for m in messages:
            if not m.metadata.agent_visible:
                continue

            current_msg_obj = {"role": m.role.value}
            
            # 临时容器
            text_parts = []
            content_list = []
            has_image = False
            
            tool_calls = []
            tool_output_msgs = []

            for content in m.content:
                # A. 文本
                if isinstance(content, TextContent):
                    if content.text:
                        text_parts.append(content.text)
                        content_list.append({"type": "text", "text": content.text})
                
                # B. 图片
                elif isinstance(content, ImageContent):
                    has_image = True
                    data_uri = f"data:{content.mime_type};base64,{content.data}"
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": data_uri}
                    })

                # C. 工具请求 (ToolRequest)
                elif isinstance(content, ToolRequest):
                    # 检查 Result 状态，只有 success 才能发给 OpenAI
                    if content.tool_call.status == "success" and content.tool_call.value:
                        # 提取内部的 CallToolRequestParam
                        param = content.tool_call.value
                        tool_calls.append({
                            "id": content.id,
                            "type": "function",
                            "function": {
                                "name": param.name,
                                "arguments": json.dumps(param.arguments or {})
                            }
                        })
                    else:
                        # 如果是 error 状态，通常不应该发给 OpenAI，或者作为纯文本展示错误
                        # 这里暂略，视业务逻辑而定
                        pass

                # D. 工具结果 (ToolResponse)
                elif isinstance(content, ToolResponse):
                    result_text = ""
                    if content.tool_result.status == "success" and content.tool_result.value:
                        for item in content.tool_result.value.content:
                            if item.text:
                                result_text += item.text
                    else:
                        # 错误情况
                        result_text = content.tool_result.error or "Unknown Error"

                    tool_output_msgs.append({
                        "role": "tool",
                        "content": result_text,
                        "tool_call_id": content.id
                    })

            # --- 组装消息体 ---
            
            # 只有当消息包含实际内容或工具调用时才添加
            if text_parts or has_image or tool_calls:
                if has_image:
                    # 强制使用 List[Dict] 格式以支持图片
                    current_msg_obj["content"] = content_list
                elif text_parts:
                    # 只有文本时，回退到 String 格式（解决 vLLM 兼容性）
                    current_msg_obj["content"] = "\n".join(text_parts)
                else:
                    # 仅有 tool_calls 的情况
                    current_msg_obj["content"] = None

                if tool_calls:
                    current_msg_obj["tool_calls"] = tool_calls
                
                openai_msgs.append(current_msg_obj)

            # 追加工具结果消息
            openai_msgs.extend(tool_output_msgs)

        return openai_msgs

    async def complete(
        self, 
        system: str, 
        messages: List[Message], 
        tools: List[Any] = []
    ) -> Tuple[Message, ProviderUsage]:
        
        openai_msgs = self._prepare_messages(system, messages)
        openai_tools = tools if tools else None

        response = await self.client.chat.completions.create(
            model=self.model_config.model_name,
            messages=openai_msgs,
            tools=openai_tools,
            temperature=self.model_config.temperature or 0.7,
        )

        choice = response.choices[0]
        # 注意：这里 content 是 List[MessageContent]，需要实例化具体的子类
        msg_content_list = []

        # 1. 处理文本回复
        if choice.message.content:
            msg_content_list.append(TextContent(text=choice.message.content))
        
        # 2. 处理工具调用
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                
                # 构造载荷
                param = CallToolRequestParam(name=tc.function.name, arguments=args)
                
                # 构造消息内容，包裹 success
                msg_content_list.append(ToolRequest(
                    id=tc.id,
                    toolCall=ToolCallResult.success(param)
                ))

        result_message = Message(
            role=Role.ASSISTANT,
            created=int(time.time()),
            content=msg_content_list
        )

        usage = Usage()
        if response.usage:
            usage = Usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )
            
            
        provider_usage = ProviderUsage(model=self.model_config.model_name, usage=usage)
        
        # [集成] 调用估算逻辑进行兜底
        # 如果 OpenAI 返回了 usage，这里什么都不会做
        # 如果是本地模型或者某些兼容层没返回 usage，这里会补全
        await ensure_usage_tokens(
            provider_usage,
            system,
            messages,
            result_message,
            tools
        )
        return result_message, provider_usage

    async def stream(
        self,
        system: str,
        messages: List[Message],
        tools: List[Any] = []
    ) -> AsyncGenerator[Tuple[Optional[Message], Optional[ProviderUsage]], None]:
        
        openai_msgs = self._prepare_messages(system, messages)
        openai_tools = tools if tools else None
        
        # 尝试开启 usage 统计 (OpenAI 特性)
        extra_body = {}
        # if "openai.com" in str(self.client.base_url):
        #     extra_body = {"stream_options": {"include_usage": True}}

        stream = await self.client.chat.completions.create(
            model=self.model_config.model_name,
            messages=openai_msgs,
            tools=openai_tools,
            stream=True,
            **extra_body
        )

        # --- [新增] 状态追踪 ---
        final_usage: Optional[ProviderUsage] = None
        accumulated_text: str = ""
        tool_call_buffer: Dict[int, Dict[str, Any]] = {}
        # --------------------

        async for chunk in stream:
            # 1. 优先处理 API 原生返回的 Usage
            if hasattr(chunk, "usage") and chunk.usage:
                usage = Usage(
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens
                )
                final_usage = ProviderUsage(model=chunk.model, usage=usage)
                yield None, final_usage
                continue

            if not chunk.choices: continue
            delta = chunk.choices[0].delta
            
            # 2. 处理文本流
            if delta.content:
                # [新增] 累积文本用于后续估算
                accumulated_text += delta.content
                
                partial = Message(
                    role=Role.ASSISTANT, 
                    content=[TextContent(text=delta.content)]
                )
                yield partial, None
            
            # 3. 处理工具流 (缓冲逻辑)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_call_buffer:
                        tool_call_buffer[idx] = {"id": "", "name": "", "args": ""}
                    
                    if tc.id: tool_call_buffer[idx]["id"] = tc.id
                    if tc.function.name: tool_call_buffer[idx]["name"] = tc.function.name
                    if tc.function.arguments: tool_call_buffer[idx]["args"] += tc.function.arguments

            # 4. 检测流结束时的工具输出
            if chunk.choices[0].finish_reason in ["tool_calls", "stop"] and tool_call_buffer:
                tool_contents = []
                for _, data in tool_call_buffer.items():
                    try:
                        args_obj = json.loads(data["args"])
                    except:
                        args_obj = {}
                    
                    param = CallToolRequestParam(name=data["name"], arguments=args_obj)
                    tool_contents.append(ToolRequest(
                        id=data["id"],
                        toolCall=ToolCallResult.success(param)
                    ))
                
                if tool_contents:
                    # 工具调用的消息也需要 yield 出去
                    yield Message(role=Role.ASSISTANT, content=tool_contents), None
                
                # 注意：tool_call_buffer 不清空，或者我们应该另存一份副本用于 full_message 构建
                # 这里为了简单，假设 tool_call_buffer 里的数据就是完整的工具调用

        # ==========================================================
        # [核心修改] 循环结束后的兜底逻辑 (Fallback)
        # 如果 API 没给 usage (final_usage 为 None)，我们必须自己算
        # ==========================================================
        if final_usage is None:
            # 1. 重构完整的回复消息 (用于计算 output tokens)
            full_content_list = []
            
            # 添加累积的文本
            if accumulated_text:
                full_content_list.append(TextContent(text=accumulated_text))
            
            # 添加累积的工具调用
            if tool_call_buffer:
                for _, data in tool_call_buffer.items():
                    try:
                        args_obj = json.loads(data["args"])
                    except:
                        args_obj = {}
                    param = CallToolRequestParam(name=data["name"], arguments=args_obj)
                    full_content_list.append(ToolRequest(
                        id=data["id"],
                        toolCall=ToolCallResult.success(param)
                    ))

            full_response_message = Message(
                role=Role.ASSISTANT,
                content=full_content_list
            )

            # 2. 创建一个空的 Usage 对象
            estimated_usage = ProviderUsage(
                model=self.model_config.model_name, 
                usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0)
            )

            # 3. 调用估算器 (它会自动计算 input 和 output)
            await ensure_usage_tokens(
                estimated_usage,
                system,
                messages,
                full_response_message, # 传入我们拼凑出的完整消息
                tools
            )
            
            # 4. 发送最后的补全 Usage
            yield None, estimated_usage