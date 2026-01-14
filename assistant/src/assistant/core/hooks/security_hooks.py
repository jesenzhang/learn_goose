"""
敏感词过滤 Hook
优先级: 20 (高优先级，在 FAQ 之后执行)
"""

import logging
import re
from typing import Optional, List, Set
from .base import AgentHook, HookResult, HookContext, HookConfig
from .manager import register_hook

logger = logging.getLogger(__name__)


@register_hook("sensitive_word_filter")
class SensitiveWordHook(AgentHook):
    """
    敏感词过滤 Hook

    检测并处理用户输入中的敏感词。
    支持从配置文件加载敏感词列表。
    """
    name = "sensitive_word_filter"
    priority = 20
    enabled = True

    def __init__(self, config: Optional[HookConfig] = None):
        super().__init__(config)

        # 从配置加载敏感词
        self.sensitive_words: Set[str] = set()
        self.replacement = "***"
        self.action = "intercept"  # intercept, replace, warn

        if config and config.params:
            self.sensitive_words = set(config.params.get("words", []))
            self.replacement = config.params.get("replacement", "***")
            self.action = config.params.get("action", "intercept")

        # 默认敏感词（示例）
        if not self.sensitive_words:
            self.sensitive_words = {
                "暴力", "恐怖", "色情", "赌博", "毒品",
                # 可根据需要添加更多
            }

    async def on_user_input(self, ctx: HookContext) -> Optional[HookResult]:
        """检测敏感词"""
        if not self.sensitive_words:
            return None

        user_input = ctx.user_input
        found_words = []

        # 简单匹配
        for word in self.sensitive_words:
            if word in user_input:
                found_words.append(word)

        if found_words:
            logger.warning(f"🚫 Sensitive words detected: {found_words}")

            if self.action == "intercept":
                return HookResult.intercept(
                    response="抱歉，您的输入包含敏感内容，请重新提问。",
                    data={"blocked_words": found_words}
                )

            elif self.action == "replace":
                cleaned_input = user_input
                for word in found_words:
                    cleaned_input = cleaned_input.replace(word, self.replacement)

                return HookResult.modify_input(cleaned_input)

            elif self.action == "warn":
                ctx.set_shared("sensitive_words_warning", found_words)

        return None


@register_hook("prompt_injection_detector")
class PromptInjectionHook(AgentHook):
    """
    Prompt 注入检测 Hook

    检测可能的 Prompt 注入攻击。
    """
    name = "prompt_injection_detector"
    priority = 30
    enabled = True

    # 常见的 Prompt 注入模式
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(all\s+)?previous\s+instructions",
        r"forget\s+(everything|all\s+instructions)",
        r"override\s+(your\s+)?(programming|instructions)",
        r"system\s*:\s*you\s+are\s+now",
        r"<\|.*?\|>",  # 特殊标记
        r"\[SYSTEM\]",
        r"\[ADMIN\]",
    ]

    def __init__(self, config: Optional[HookConfig] = None):
        super().__init__(config)
        self.patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

        if config and config.params:
            custom_patterns = config.params.get("patterns", [])
            for p in custom_patterns:
                try:
                    self.patterns.append(re.compile(p, re.IGNORECASE))
                except re.error:
                    logger.warning(f"Invalid regex pattern: {p}")

    async def on_user_input(self, ctx: HookContext) -> Optional[HookResult]:
        """检测 Prompt 注入"""
        user_input = ctx.user_input

        for pattern in self.patterns:
            if pattern.search(user_input):
                logger.warning(f"🚫 Potential prompt injection detected: {pattern.pattern}")
                return HookResult.intercept(
                    response="抱歉，您的输入看起来像是在尝试注入指令。请直接描述您的需求。",
                    data={"reason": "prompt_injection", "pattern": pattern.pattern}
                )

        return None
