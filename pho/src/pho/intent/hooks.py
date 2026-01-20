from typing import Dict, Any
from ..skills.context import ServiceContext

def slot_to_instruction(slots: Dict[str, Any], ctx: ServiceContext) -> str:
    """
    通用 Hook：将提取到的 Slot 转换为自然语言指令。
    需要在 Intent 配置中通过 skill_params 定义 'template'。
    """
    # 从 shared_memory 中获取配置的模板（因为在 MicroAgent 中 skill_params 被 update 到了 shared_memory）
    # 或者，更好的方式是 IntentExecutor 直接把 config 传给 hook，但目前的签名不支持。
    # 变通方案：我们在 YAML 里把模板定义在 skill_params 里，MicroAgent 会把它注入到 shared_memory。
    
    template = ctx.state.shared_memory.get("_instruction_template")
    
    if not template:
        # 默认回退逻辑
        params_str = ", ".join(f"{k}={v}" for k, v in slots.items())
        return f"请使用当前技能处理这些参数: {params_str}"
        
    try:
        # 使用 Jinja2 或简单的 format
        return template.format(**slots)
    except KeyError as e:
        return f"指令生成失败 (缺失参数 {e}): {template}"