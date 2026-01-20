"""
Hook System Base Definitions
Enhanced hook system with complete lifecycle support, data flow pipeline, and configuration.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict, List, Callable, TypeVar, Generic
from ..state import AgentState
from ..generation import AgentGeneration
from ..context import RequestContext


# ==================== Hook Action Types ====================

class HookAction(str, Enum):
    """Hook 执行动作类型"""
    CONTINUE = "continue"           # 继续执行后续流程
    INTERCEPT = "intercept"         # 拦截流程，直接返回响应
    MODIFY = "modify"               # 修改数据后继续
    SKIP = "skip"                   # 跳过当前步骤
    RETRY = "retry"                 # 重试当前操作


# ==================== Enhanced Hook Result ====================

@dataclass
class HookResult:
    """
    Hook 执行结果（增强版）

    支持多种操作类型和数据流动控制
    """
    # 动作类型
    action: HookAction = HookAction.CONTINUE

    # 响应相关（当 action=INTERCEPT 时使用）
    response: Optional[str] = None
    response_data: Optional[Any] = None  # 结构化响应数据

    # 修改相关（当 action=MODIFY 时使用）
    modified_input: Optional[str] = None
    modified_data: Optional[Dict[str, Any]] = None

    # 重试相关（当 action=RETRY 时使用）
    retry_after: Optional[float] = None  # 重试延迟（秒）
    retry_reason: Optional[str] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 是否立即生效（某些场景可能需要延迟）
    immediate: bool = True

    @classmethod
    def continue_(cls) -> "HookResult":
        """继续执行"""
        return cls(action=HookAction.CONTINUE)

    @classmethod
    def intercept(cls, response: str, response_data: Any = None) -> "HookResult":
        """拦截并返回响应"""
        return cls(
            action=HookAction.INTERCEPT,
            response=response,
            response_data=response_data
        )

    @classmethod
    def modify_input(cls, new_input: str) -> "HookResult":
        """修改输入"""
        return cls(
            action=HookAction.MODIFY,
            modified_input=new_input
        )

    @classmethod
    def modify_data(cls, data: Dict[str, Any]) -> "HookResult":
        """修改数据"""
        return cls(
            action=HookAction.MODIFY,
            modified_data=data
        )

    @classmethod
    def skip(cls) -> "HookResult":
        """跳过当前步骤"""
        return cls(action=HookAction.SKIP)

    @classmethod
    def retry(cls, reason: str, delay: float = 0) -> "HookResult":
        """重试"""
        return cls(
            action=HookAction.RETRY,
            retry_reason=reason,
            retry_after=delay
        )

    @property
    def is_final(self) -> bool:
        """是否终止后续流程"""
        return self.action in (HookAction.INTERCEPT, HookAction.SKIP)

    @property
    def should_modify(self) -> bool:
        """是否需要修改数据"""
        return self.action == HookAction.MODIFY


# ==================== Hook Context ====================

@dataclass
class HookContext:
    """
    Hook 执行上下文
    用于在 Hook 之间传递共享数据
    """
    user_input: str
    state: AgentState
    gen: AgentGeneration
    req_ctx: RequestContext

    # 共享数据存储
    shared_data: Dict[str, Any] = field(default_factory=dict)

    # 执行追踪
    executed_hooks: List[str] = field(default_factory=list)
    skipped_hooks: List[str] = field(default_factory=list)

    # 性能统计
    start_time: float = field(default_factory=time.time)

    def get_shared(self, key: str, default: Any = None) -> Any:
        """获取共享数据"""
        return self.shared_data.get(key, default)

    def set_shared(self, key: str, value: Any) -> None:
        """设置共享数据"""
        self.shared_data[key] = value

    def mark_executed(self, hook_name: str) -> None:
        """标记 Hook 已执行"""
        self.executed_hooks.append(hook_name)

    def mark_skipped(self, hook_name: str, reason: str = "") -> None:
        """标记 Hook 已跳过"""
        self.skipped_hooks.append(f"{hook_name}:{reason}")

    @property
    def elapsed_time(self) -> float:
        """获取已用时间（秒）"""
        return time.time() - self.start_time


# ==================== Hook Configuration ====================

@dataclass
class HookConfig:
    """Hook 配置（从配置文件加载）"""
    name: str
    enabled: bool = True
    priority: int = 100

    # Hook 类型
    hook_type: str = "filter"  # filter, transformer, observer, validator

    # 执行条件
    conditions: Dict[str, Any] = field(default_factory=dict)

    # 配置参数
    params: Dict[str, Any] = field(default_factory=dict)

    # 失败处理
    fail_on_error: bool = False
    error_message: Optional[str] = None


# ==================== Base Hook Class ====================

class AgentHook(ABC):
    """
    Agent 生命周期钩子基类（增强版）

    Hook 执行优先级：
    - 0-49: 系统 Hook（FAQ、敏感词等）
    - 50-99: 验证 Hook（输入验证、权限检查等）
    - 100-149: 转换 Hook（数据转换、格式化等）
    - 150-199: 观察 Hook（日志、统计等）
    - 200+: 自定义 Hook
    """

    # Hook 基本信息
    name: str = "base_hook"
    priority: int = 100
    enabled: bool = True

    # Hook 配置
    config: HookConfig = None

    def __init__(self, config: Optional[HookConfig] = None):
        if config:
            self.config = config
            self.name = config.name
            self.priority = config.priority
            self.enabled = config.enabled

    # ==================== 请求生命周期 Hooks ====================

    async def on_request_start(self, ctx: HookContext) -> Optional[HookResult]:
        """
        请求开始时触发（最早执行的 Hook）
        用途：初始化、权限检查、请求日志等
        """
        return None

    async def on_request_end(self, ctx: HookContext, result: Optional[Any] = None) -> Optional[HookResult]:
        """
        请求结束时触发（最后执行的 Hook）
        用途：清理、日志记录、统计汇总等
        """
        return None

    # ==================== 输入处理 Hooks ====================

    async def on_user_input(self, ctx: HookContext) -> Optional[HookResult]:
        """
        处理用户输入时触发（核心 Hook 点）

        常见用途：
        - FAQ 拦截（优先级 10）
        - 敏感词过滤（优先级 20）
        - Prompt 注入检测（优先级 30）
        - 输入验证（优先级 50）
        - 输入转换/清洗（优先级 100）
        """
        return None

    async def on_input_validated(self, ctx: HookContext) -> Optional[HookResult]:
        """
        输入验证后触发
        用途：验证后的处理、数据增强等
        """
        return None

    # ==================== 意图识别 Hooks ====================

    async def on_intent_detect_start(self, ctx: HookContext) -> Optional[HookResult]:
        """意图识别开始前触发"""
        return None

    async def on_intent_detected(self, ctx: HookContext, intent_data: Any) -> Optional[HookResult]:
        """
        意图识别后触发
        用途：意图验证、意图修改、意图拦截等
        """
        return None

    # ==================== 工具执行 Hooks ====================

    async def on_tool_start(self, ctx: HookContext, tool_name: str, args: Dict[str, Any]) -> Optional[HookResult]:
        """
        工具执行前触发
        用途：参数验证、权限检查、工具替换等
        """
        return None

    async def on_tool_end(self, ctx: HookContext, tool_name: str, args: Dict[str, Any], result: Any) -> Optional[HookResult]:
        """
        工具执行后触发
        用途：结果验证、结果转换、结果过滤等
        """
        return None

    async def on_tool_error(self, ctx: HookContext, tool_name: str, error: Exception) -> Optional[HookResult]:
        """
        工具执行错误时触发
        用途：错误处理、错误转换、重试决策等
        """
        return None

    # ==================== 响应生成 Hooks ====================

    async def on_response_generate(self, ctx: HookContext) -> Optional[HookResult]:
        """
        响应生成前触发
        用途：响应模板选择、格式控制等
        """
        return None

    async def on_response_generated(self, ctx: HookContext, response: str) -> Optional[HookResult]:
        """
        响应生成后触发
        用途：内容过滤、敏感信息脱敏、格式化等
        """
        return None

    # ==================== 错误处理 Hooks ====================

    async def on_error(self, ctx: HookContext, error: Exception) -> Optional[HookResult]:
        """
        全局错误处理
        用途：错误日志、错误转换、友好错误消息等
        """
        return None

    # ==================== 辅助方法 ====================

    def should_execute(self, ctx: HookContext) -> bool:
        """判断是否应该执行此 Hook"""
        if not self.enabled:
            return False

        # 检查配置中的条件
        if self.config and self.config.conditions:
            return self._check_conditions(ctx, self.config.conditions)

        return True

    def _check_conditions(self, ctx: HookContext, conditions: Dict[str, Any]) -> bool:
        """
        检查执行条件

        Args:
            ctx: Hook 执行上下文
            conditions: 条件配置字典

        Returns:
            True 如果应该执行此 Hook
        """
        user_input = ctx.user_input
        session_id = ctx.state.session_id

        # 检查用户 ID
        user_ids = conditions.get("user_ids")
        if user_ids:
            # 从 context 中获取 user_id，如果没有则跳过此检查
            user_id = getattr(ctx.req_ctx, "user_id", None)
            if user_id not in user_ids:
                return False

        # 检查会话 ID
        session_ids = conditions.get("session_ids")
        if session_ids and session_id not in session_ids:
            return False

        # 检查输入长度
        min_length = conditions.get("min_length")
        if min_length is not None and len(user_input) < min_length:
            return False

        max_length = conditions.get("max_length")
        if max_length is not None and len(user_input) > max_length:
            return False

        # 检查包含关键词
        contains = conditions.get("contains")
        if contains:
            if not any(keyword in user_input for keyword in contains):
                return False

        # 检查不包含关键词
        not_contains = conditions.get("not_contains")
        if not_contains:
            if any(keyword in user_input for keyword in not_contains):
                return False

        # 自定义条件（可由子类覆盖）
        custom = conditions.get("custom")
        if custom:
            return self._check_custom_conditions(ctx, custom)

        return True

    def _check_custom_conditions(self, ctx: HookContext, custom: Dict[str, Any]) -> bool:
        """
        检查自定义条件

        子类可以覆盖此方法以实现更复杂的条件逻辑。

        Args:
            ctx: Hook 执行上下文
            custom: 自定义条件字典

        Returns:
            True 如果自定义条件满足
        """
        # 默认实现：所有自定义条件都通过
        return True
