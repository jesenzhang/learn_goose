from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from pho.components.base import Component
from pho.sandbox import ICodeSandbox,NativeSandboxAdapter
from pho.utils.template import TemplateRenderer
from pho.toolkit import tool_registry, ToolSourceType
from pho.types import InputMapping
from pho.components.registry import register_component
from pho.types import NodeTypes

# --- CodeRunner Config ---
class CodeConfig(BaseModel):
    # 输入参数列表 (对应 Coze 的 input parameters)
    input_parameters: List[InputMapping] = Field(default_factory=list, alias="inputParameters")
    
    # 用户代码字符串
    code: str = Field(..., description="用户代码")
    
    # 超时设置
    timeout: int = Field(30, description="超时时间(秒)")

@register_component(
    name=NodeTypes.CODE_RUNNER,
    group="Code",
    label="代码执行 (Python)",
    description="编写 Python 代码处理变量",
    icon="code",
    author="System",
    version="1.0.0",
    config_model=CodeConfig,
    input_model=None
)
class CodeRunner(Component):
    # 默认使用本地沙箱，生产环境应注入 DockerSandbox
    _sandbox: ICodeSandbox = NativeSandboxAdapter()

    async def execute(self, inputs: Dict[str, Any], config: CodeConfig) -> Dict[str, Any]:
        # 1. [参数准备]
        # 将 input_parameters 列表转换为扁平的字典，并处理变量渲染
        code_inputs = {}
        
        # 优先使用 config 定义的参数映射
        for param in config.input_parameters:
            val = param.value
            # 如果是字符串，尝试渲染
            if isinstance(val, str):
                val = TemplateRenderer.render(val, inputs)
            code_inputs[param.name] = val
        
        # 如果 config 没有定义参数 (兼容性)，则尝试直接透传 inputs
        if not code_inputs and inputs:
            code_inputs = inputs

        print(f" 💻 [Code] Running with inputs: {list(code_inputs.keys())}")

        # 2. [沙箱执行]
        try:
            result = await self._sandbox.run_code(
                code=config.code,
                inputs=code_inputs,
                timeout=config.timeout
            )
            
            # 3. [错误检查]
            if isinstance(result, dict) and "error" in result:
                # 可以选择抛出异常中断流程，或者返回错误信息
                raise RuntimeError(f"Code Execution Error: {result['error']}\n{result.get('traceback', '')}")
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"Sandbox Failed: {str(e)}")

# --- Lambda Component (本地预定义函数) ---

class LambdaConfig(BaseModel):
    function_name: str = Field(..., description="预注册的函数名")
    args: Dict[str, Any] = Field(default_factory=dict, description="固定参数")

@register_component(
    name=NodeTypes.LAMBDA,
    group="Code",
    label="Lambda 函数",
    description="调用系统预置的 Python 函数",
    icon="function",
    author="System",
    version="1.0.0",
    config_model=LambdaConfig
)
class Lambda(Component):
    async def execute(self, inputs: Dict[str, Any], config: LambdaConfig) -> Dict[str, Any]:
        # 需要一个 Lambda 注册表。
        # 这里为了演示，我们假设存在一个全局注册表，或者通过 SystemRegistry 获取

        # 1. 查找函数定义
        # 我们复用 ToolDefinitionRegistry，假设 Lambda 被注册为 BUILTIN 工具
        tool_def = tool_registry.get(config.function_name)

        if not tool_def or tool_def.source_type != ToolSourceType.BUILTIN:
             # 回退：尝试直接查找 Python 内存对象 (如果有一个简单的 dict 注册表)
             # 这里简单模拟
             raise ValueError(f"Lambda '{config.function_name}' not found or not a builtin function")

        func = tool_def.function
        if not func:
            raise ValueError(f"Function implementation for '{config.function_name}' is missing")

        # 2. 参数合并
        # inputs (运行时参数) 覆盖 config.args (固定参数)
        merged_args = {**config.args, **inputs}
        
        print(f" ⚡ [Lambda] Calling {config.function_name}")

        # 3. 执行
        import inspect
        if inspect.iscoroutinefunction(func):
            result = await func(**merged_args)
        else:
            result = func(**merged_args)
            
        # 4. 格式化输出
        if isinstance(result, dict):
            return result
        return {"output": result}