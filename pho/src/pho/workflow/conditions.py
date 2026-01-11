# src/goose/workflow/conditions.py

from typing import Any, Callable, Dict,List,Tuple
from .context import WorkflowContext
from .resolver import ValueResolver
import logging
logger = logging.getLogger("goose.workflow.condition")

class Condition:
    """
    Coze 风格的条件路由助手。
    用法:
    router = Condition("{{ check.score }}") \
                .if_match(lambda x: x > 60, "pass_node") \
                .else_goto("fail_node")
    """
    def __init__(self, selector: str):
        self.selector = selector # e.g., "{{ check.score }}"
        self.rules: List[Tuple[Callable, str]] = []
        self.default_node: str = "__END__"

    def if_match(self, predicate: Callable[[Any], bool], target_node: str):
        self.rules.append((predicate, target_node))
        return self

    def else_goto(self, target_node: str):
        self.default_node = target_node
        return self # Fluent API

    def __call__(self, context: WorkflowContext) -> str:
        """Scheduler 会调用这个方法"""
        # 1. 解析值
        # 这里借用 ValueResolver 的 _resolve_string 逻辑，或者直接用 ValueResolver.resolve
        # 但我们只要单值，所以包装一下
        val = ValueResolver.resolve(self.selector, context)
        
        logger.info(f"🔀 Condition Check: {self.selector} = {val}")

        # 2. 匹配规则
        for predicate, target in self.rules:
            try:
                if predicate(val):
                    logger.info(f"   Matched rule -> {target}")
                    return target
            except Exception:
                continue
                
        logger.info(f"   No match, default -> {self.default_node}")
        return self.default_node