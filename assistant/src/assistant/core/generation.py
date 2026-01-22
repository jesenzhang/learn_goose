import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional,Callable
import inspect
from ..providers.base import BaseLLM

# Core Imports
from ..config.loader import ConfigLoader
from ..skills import SkillLoader

# Intent Imports
from ..intent.recognizer import IntentRecognizer
from ..intent.strategy import IntentExecutor
logger = logging.getLogger(__name__)

@dataclass
class AgentGeneration:
    """
    代表"一代"配置和组件实例。
    管理资源的生命周期，确保在所有引用结束前不关闭资源。
    """
    version: str  # 比如 UUID 或 时间戳
    config: ConfigLoader
    llm: BaseLLM
    ai_services: Dict[str, Any]
    intent_recognizer: IntentRecognizer
    intent_executor: IntentExecutor
    core_tools: Dict[str, Callable]
    skill_loader: SkillLoader
    
    # 引用计数状态
    _active_count: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _all_done_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _is_retired: bool = field(default=False, init=False)

    def __post_init__(self):
        self._all_done_event.set() # 初始状态为 Done (0引用)

    @property
    def active_count(self) -> int:
        return self._active_count

    async def acquire(self):
        """请求开始：计数 +1"""
        async with self._lock:
            self._active_count += 1
            self._all_done_event.clear()

    async def release(self):
        """请求结束：计数 -1"""
        async with self._lock:
            self._active_count -= 1
            if self._active_count <= 0:
                self._active_count = 0
                self._all_done_event.set() # 通知可以关闭了

    def context_scope(self):
        """
        辅助 Context Manager，用于 run_task 中的 with 语句
        """
        return GenerationScope(self)

    async def drain_and_close(self):
        """
        [阻塞] 等待所有现有请求完成，然后关闭资源。
        通常在后台 Task 中运行。
        """
        self._is_retired = True
        logger.info(f"⏳ Generation {self.version} retiring... Waiting for {self._active_count} active tasks.")
        
        # 1. 等待计数归零
        await self._all_done_event.wait()
        
        logger.info(f"🗑️ Generation {self.version} drained. Closing resources...")
        
        # 2. 执行关闭逻辑
        try:
            # 关闭 LLM
            if hasattr(self.llm, 'aclose'): 
                if inspect.iscoroutinefunction(self.llm.aclose):
                    await self.llm.aclose()
                else:
                    self.llm.aclose()
            elif hasattr(self.llm, 'close'): 
                if inspect.iscoroutinefunction(self.llm.close):
                    await self.llm.close()
                else:
                    self.llm.close()

            # 关闭 AI Services
            for svc in self.ai_services.values():
                if hasattr(svc, 'aclose'): 
                    if inspect.iscoroutinefunction(svc.aclose):
                        await svc.aclose()
                    else:
                        svc.aclose()
                elif hasattr(svc, 'close'): 
                    if inspect.iscoroutinefunction(svc.close):
                        await svc.close()
                    else:
                        svc.close()
        except Exception as e:
            logger.error(f"Error while closing resources for Generation {self.version}: {e}", exc_info=e)
            
        logger.info(f"💀 Generation {self.version} fully closed.")

class GenerationScope:
    """Helper for async with syntax"""
    def __init__(self, gen: AgentGeneration):
        self.gen = gen
    
    async def __aenter__(self):
        await self.gen.acquire()
        return self.gen
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.gen.release()