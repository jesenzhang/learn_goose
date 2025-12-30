import asyncio
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from simpleeval import SimpleEval

# --- 核心层依赖 (无 Adapter 依赖) ---
from goose.components.base import Component
from goose.resources.ui import UI
from goose.workflow.protocol import WorkflowDefinition 
from goose.workflow.converter import WorkflowConverter 
from goose.workflow.scheduler import WorkflowScheduler
from goose.components.registry import register_component
from goose.types import NodeTypes
# ==========================================
# 1. Selector (If-Else)
# ==========================================

class ConditionBranch(BaseModel):
    """分支条件定义"""
    expression: str = Field(..., description="条件表达式 (e.g. score > 60)")
    target_handle: str = Field(..., description="目标句柄 ID")

class SelectorConfig(BaseModel):
    conditions: List[ConditionBranch] = Field(
        default_factory=list,
        json_schema_extra=UI.Combo(model_class=ConditionBranch)
    )
    default_handle: str = Field("else", description="默认分支句柄")

@register_component(
    name=NodeTypes.SELECTOR,
    group="Control",
    label="条件分支",
    description="根据条件分支执行不同路径",
    icon="git-branch",
    author="System",
    version="1.0.0",
    config_model=SelectorConfig
)
class SelectorComponent(Component):
    async def execute(self, inputs: Dict[str, Any], config: SelectorConfig) -> Dict[str, Any]:
        evaluator = SimpleEval(names=inputs)
        
        for branch in config.conditions:
            try:
                # 评估表达式
                if evaluator.eval(branch.expression):
                    # 返回特殊的路由信号，Scheduler 会识别 _active_handle
                    return {
                        "_active_handle": branch.target_handle,
                        "result": True,
                        "selected_branch": branch.expression
                    }
            except Exception as e:
                # 记录日志，但不中断，尝试后续分支
                print(f"Selector eval error: {e}")

        # 默认分支
        return {
            "_active_handle": config.default_handle,
            "result": False,
            "selected_branch": "default"
        }


# ==========================================
# 2. Loop (循环)
# ==========================================

class LoopConfig(BaseModel):
    loop_type: Literal["array", "count"] = Field("array", description="循环类型")
    count: int = Field(1, description="循环次数 (Count模式)")
    
    # [关键] 这里接收的是 Goose 内部标准的 WorkflowDefinition
    # Adapter 层必须在创建此节点前，将 VueFlow JSON 转换为此标准对象
    sub_workflow: WorkflowDefinition = Field(..., description="子工作流定义")

@register_component(
    name=NodeTypes.LOOP,
    group="Control",
    label="循环",
    description="循环执行子工作流",
    icon="repeat",
    author="System",
    version="1.0.0",
    config_model=LoopConfig
)
class LoopComponent(Component):

    async def execute(self, inputs: Dict[str, Any], config: LoopConfig) -> Dict[str, Any]:
        # 1. 确定迭代对象
        items = []
        if config.loop_type == "array":
            # 策略：查找第一个列表输入
            for val in inputs.values():
                if isinstance(val, list):
                    items = val
                    break
            if not items and inputs: items = [inputs] # 容错
        else:
            # Count 模式
            # 支持动态输入覆盖配置 (inputs['count'] > config.count)
            count_val = inputs.get("count", config.count)
            items = list(range(int(count_val)))

        # 2. 编译子图 (Runtime Compilation)
        # 使用核心层的 Converter，将 Protocol 定义转为 Executable Graph
        # 注意：这里我们每次执行都重新编译，或者可以在 __init__ 中做缓存
        converter = WorkflowConverter()
        sub_graph = converter.convert(config.sub_workflow)
        
        results = []
        
        # 3. 串行执行
        for i, item in enumerate(items):
            # 注入循环变量
            iteration_inputs = inputs.copy()
            iteration_inputs.update({
                "loop_item": item,
                "loop_index": i,
                "item": item, 
                "index": i
            })
            
            # 创建子调度器
            sub_scheduler = WorkflowScheduler(sub_graph)
            
            try:
                # 运行子图
                # run_to_completion 是 Scheduler 的辅助方法，负责收集最终结果
                run_result = await sub_scheduler.run_to_completion(iteration_inputs)
                
                # 4. 处理控制信号 (Break/Continue)
                control = run_result.get("_control_signal")
                if control == "BREAK":
                    break
                if control == "CONTINUE":
                    continue
                    
                results.append(run_result)
                
            except Exception as e:
                # Fail-Soft 策略
                results.append({"error": str(e), "loop_index": i})

        return {
            "results": results,
            "count": len(results)
        }


# ==========================================
# 3. Batch (并行批处理)
# ==========================================

class BatchConfig(BaseModel):
    batch_size: int = Field(5, description="并发大小")
    # 同样接收标准定义
    sub_workflow: WorkflowDefinition = Field(..., description="子工作流定义")

@register_component(
    name=NodeTypes.BATCH,
    group="Control",
    label="批处理",
    description="并行执行子工作流",
    icon="layers",
    author="System",
    version="1.0.0",
    config_model=BatchConfig
)
class BatchComponent(Component):
    async def execute(self, inputs: Dict[str, Any], config: BatchConfig) -> Dict[str, Any]:
        raw_list = inputs.get("input_list", [])
        if not isinstance(raw_list, list):
            raw_list = []

        # 1. 编译子图
        converter = WorkflowConverter()
        sub_graph = converter.convert(config.sub_workflow)

        results = []
        
        # 2. 信号量控制并发
        semaphore = asyncio.Semaphore(config.batch_size)

        async def worker(item, idx):
            async with semaphore:
                iteration_inputs = {"batch_item": item, "batch_index": idx}
                sub_scheduler = WorkflowScheduler(sub_graph)
                # Batch 通常不处理 Break/Continue，因为是并发的
                return await sub_scheduler.run_to_completion(iteration_inputs)

        # 3. 并发执行
        tasks = [worker(item, i) for i, item in enumerate(raw_list)]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 异常处理
            results = [str(r) if isinstance(r, Exception) else r for r in results]

        return {"results": results}


# ==========================================
# 4. 信号组件 (Break / Continue)
# ==========================================

@register_component(
    name=NodeTypes.BREAK,
    group="Control",
    label="跳出",
    description="跳出当前循环",
    icon="x-circle",
    author="System",
    version="1.0.0"
)
class BreakComponent(Component):
    async def execute(self, inputs: Dict, config: Dict) -> Dict:
        # 发送信号，Loop 组件会捕获这个 Key
        return {"_control_signal": "BREAK"}

@register_component(
    name=NodeTypes.CONTINUE,
    group="Control",
    label="继续",
    description="继续当前循环",
    icon="skip-forward",
    author="System",
    version="1.0.0"
)
class ContinueComponent(Component):
    async def execute(self, inputs: Dict, config: Dict) -> Dict:
        return {"_control_signal": "CONTINUE"}