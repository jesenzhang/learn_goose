"""
Scheduler Module

任务调度器，支持：
- Cron 表达式调度
- 一次性延迟任务
- 持久化任务列表
- 任务执行历史
- 暂停/恢复任务

Reference: goose-rs/crates/goose/src/scheduler.rs
"""

import json
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from abc import ABC, abstractmethod

logger = logging.getLogger("goose.scheduler")


class SchedulerError(Exception):
    """调度器错误"""
    
    def __init__(self, message: str, code: str = "SCHEDULER_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class JobStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class ScheduledJob:
    """计划任务"""
    id: str
    name: str
    cron_expression: str
    task_type: str = "one_shot"
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    last_status: JobStatus = JobStatus.PENDING
    current_session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["last_status"] = self.last_status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledJob":
        if "last_status" in data and isinstance(data["last_status"], str):
            data["last_status"] = JobStatus(data["last_status"])
        return cls(**data)


@dataclass
class JobExecution:
    """任务执行记录"""
    job_id: str
    session_id: Optional[str]
    started_at: str
    completed_at: Optional[str] = None
    status: JobStatus = JobStatus.RUNNING
    result: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0


class TaskCallback(ABC):
    """任务回调抽象类"""
    
    @abstractmethod
    async def execute(
        self,
        job_id: str,
        job_name: str,
        metadata: Dict[str, Any]
    ) -> str:
        """执行任务，返回结果"""
        pass


class Scheduler:
    """
    任务调度器
    
    功能：
    - Cron 表达式调度
    - 一次性延迟任务
    - 任务持久化
    - 暂停/恢复
    - 执行历史
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        timezone: str = "local"
    ):
        """
        初始化调度器
        
        Args:
            storage_path: 任务存储文件路径
            timezone: 时区
        """
        self.storage_path = storage_path or "./data/schedule.json"
        self.timezone = timezone
        
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running_jobs: Dict[str, asyncio.Task] = {}
        self._execution_history: List[JobExecution] = []
        self._task_callbacks: Dict[str, TaskCallback] = {}
        self._lock = asyncio.Lock()
        
        self._setup_storage()
    
    def _setup_storage(self) -> None:
        """设置存储目录"""
        path = Path(self.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
    
    def register_task_type(
        self,
        task_type: str,
        callback: TaskCallback
    ) -> None:
        """注册任务类型处理器"""
        self._task_callbacks[task_type] = callback
    
    async def add_job(
        self,
        name: str,
        cron_expression: str,
        task_type: str = "one_shot",
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ScheduledJob:
        """
        添加计划任务
        
        Args:
            name: 任务名称
            cron_expression: Cron 表达式 (5-6 字段)
            task_type: 任务类型
            enabled: 是否启用
            metadata: 附加数据
            
        Returns:
            创建的任务
        """
        async with self._lock:
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            
            job = ScheduledJob(
                id=job_id,
                name=name,
                cron_expression=cron_expression,
                task_type=task_type,
                enabled=enabled,
                metadata=metadata or {}
            )
            
            self._jobs[job_id] = job
            
            await self._persist_jobs()
            logger.info(f"Added scheduled job: {job_id} ({name})")
            
            return job
    
    async def remove_job(self, job_id: str) -> bool:
        """
        删除任务
        
        Args:
            job_id: 任务 ID
            
        Returns:
            是否成功删除
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False
            
            del self._jobs[job_id]
            
            if job_id in self._running_jobs:
                self._running_jobs[job_id].cancel()
                del self._running_jobs[job_id]
            
            await self._persist_jobs()
            logger.info(f"Removed scheduled job: {job_id}")
            
            return True
    
    async def pause_job(self, job_id: str) -> bool:
        """
        暂停任务
        
        Args:
            job_id: 任务 ID
            
        Returns:
            是否成功暂停
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            job.enabled = False
            job.last_status = JobStatus.PAUSED
            job.updated_at = datetime.now(timezone.utc).isoformat()
            
            await self._persist_jobs()
            logger.info(f"Paused scheduled job: {job_id}")
            
            return True
    
    async def resume_job(self, job_id: str) -> bool:
        """
        恢复任务
        
        Args:
            job_id: 任务 ID
            
        Returns:
            是否成功恢复
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False
            
            job = self._jobs[job_id]
            job.enabled = True
            job.last_status = JobStatus.SCHEDULED
            job.updated_at = datetime.now(timezone.utc).isoformat()
            
            await self._persist_jobs()
            logger.info(f"Resumed scheduled job: {job_id}")
            
            return True
    
    async def run_job_now(self, job_id: str) -> Optional[JobExecution]:
        """
        立即运行任务
        
        Args:
            job_id: 任务 ID
            
        Returns:
            执行记录
        """
        async with self._lock:
            if job_id not in self._jobs:
                return None
            
            job = self._jobs[job_id]
            
            if job.last_status == JobStatus.RUNNING:
                raise SchedulerError(f"Job '{job_id}' is already running", "JOB_RUNNING")
            
            job.last_status = JobStatus.RUNNING
            job.updated_at = datetime.now(timezone.utc).isoformat()
            await self._persist_jobs()
        
        execution = await self._execute_job(job)
        return execution
    
    async def list_jobs(self) -> List[ScheduledJob]:
        """列出所有任务"""
        async with self._lock:
            return list(self._jobs.values())
    
    async def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """获取任务"""
        async with self._lock:
            return self._jobs.get(job_id)
    
    async def get_job_executions(
        self,
        job_id: Optional[str] = None,
        limit: int = 50
    ) -> List[JobExecution]:
        """获取执行历史"""
        async with self._lock:
            if job_id:
                return [e for e in self._execution_history if e.job_id == job_id][-limit:]
            return self._execution_history[-limit:]
    
    async def schedule_immediate(
        self,
        name: str,
        task_type: str,
        delay_seconds: float = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ScheduledJob:
        """
        安排立即执行的任务
        
        Args:
            name: 任务名称
            task_type: 任务类型
            delay_seconds: 延迟秒数
            metadata: 附加数据
            
        Returns:
            创建的任务
        """
        async with self._lock:
            job_id = f"immediate_{uuid.uuid4().hex[:8]}"
            
            run_at = datetime.now(timezone.utc)
            if delay_seconds > 0:
                run_at = run_at.fromtimestamp(run_at.timestamp() + delay_seconds)
            
            job = ScheduledJob(
                id=job_id,
                name=name,
                cron_expression="@once",
                task_type=task_type,
                enabled=True,
                next_run=run_at.isoformat(),
                metadata=metadata or {}
            )
            
            self._jobs[job_id] = job
            
            if delay_seconds == 0:
                asyncio.create_task(self._execute_job(job))
            else:
                async def delayed_execute():
                    await asyncio.sleep(delay_seconds)
                    await self._execute_job(job)
                asyncio.create_task(delayed_execute())
            
            logger.info(f"Scheduled immediate job: {job_id}")
            return job
    
    async def _execute_job(self, job: ScheduledJob) -> JobExecution:
        """执行任务"""
        execution = JobExecution(
            job_id=job.id,
            session_id=job.current_session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            status=JobStatus.RUNNING
        )
        
        self._execution_history.append(execution)
        
        callback = self._task_callbacks.get(job.task_type)
        
        if callback is None:
            result = f"No handler for task type: {job.task_type}"
            execution.status = JobStatus.FAILED
            execution.error = result
        else:
            try:
                result = await callback.execute(
                    job_id=job.id,
                    job_name=job.name,
                    metadata=job.metadata
                )
                execution.status = JobStatus.COMPLETED
                execution.result = result
            except Exception as e:
                execution.status = JobStatus.FAILED
                execution.error = str(e)
                logger.error(f"Job {job.id} failed: {e}")
        
        execution.completed_at = datetime.now(timezone.utc).isoformat()
        execution.duration_seconds = (
            datetime.fromisoformat(execution.completed_at.replace("+00:00", "")) -
            datetime.fromisoformat(execution.started_at.replace("+00:00", ""))
        ).total_seconds()
        
        async with self._lock:
            job.last_run = execution.completed_at
            job.last_status = execution.status
            job.updated_at = datetime.now(timezone.utc).isoformat()
            
            if job.cron_expression == "@once":
                job.enabled = False
                job.last_status = JobStatus.COMPLETED
            
            if job.id in self._running_jobs:
                del self._running_jobs[job.id]
            
            await self._persist_jobs()
        
        logger.info(
            f"Job {job.id} completed with status: {execution.status.value} "
            f"({execution.duration_seconds:.2f}s)"
        )
        
        return execution
    
    async def kill_job(self, job_id: str) -> bool:
        """终止运行中的任务"""
        async with self._lock:
            if job_id not in self._running_jobs:
                return False
        
        task = self._running_jobs.get(job_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            async with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id].last_status = JobStatus.CANCELLED
                del self._running_jobs[job_id]
                await self._persist_jobs()
            
            logger.info(f"Killed job: {job_id}")
            return True
        
        return False
    
    async def get_running_jobs(self) -> List[str]:
        """获取运行中的任务列表"""
        async with self._lock:
            return list(self._running_jobs.keys())
    
    async def clear_history(self, before_days: int = 7) -> int:
        """
        清理历史记录
        
        Args:
            before_days: 清理此天数前的记录
            
        Returns:
            删除的记录数
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (before_days * 86400)
        
        async with self._lock:
            original_count = len(self._execution_history)
            self._execution_history = [
                e for e in self._execution_history
                if datetime.fromisoformat(e.started_at.replace("+00:00", "")).timestamp() > cutoff
            ]
            return original_count - len(self._execution_history)
    
    async def shutdown(self) -> None:
        """关闭调度器"""
        async with self._lock:
            for task in self._running_jobs.values():
                task.cancel()
            self._running_jobs.clear()
            await self._persist_jobs()
        logger.info("Scheduler shutdown complete")
    
    async def _persist_jobs(self) -> None:
        """持久化任务列表"""
        try:
            path = Path(self.storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            jobs_data = [job.to_dict() for job in self._jobs.values()]
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(jobs_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to persist jobs: {e}")
    
    async def load_jobs(self) -> None:
        """从存储加载任务列表"""
        path = Path(self.storage_path)
        if not path.exists():
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                jobs_data = json.load(f)
            
            async with self._lock:
                for job_data in jobs_data:
                    job = ScheduledJob.from_dict(job_data)
                    self._jobs[job.id] = job
            
            logger.info(f"Loaded {len(jobs_data)} scheduled jobs")
        except Exception as e:
            logger.error(f"Failed to load jobs: {e}")


class SimpleAgentTask(TaskCallback):
    """简单的 Agent 任务回调"""
    
    def __init__(self, agent_factory: Callable[[], Any]):
        """
        初始化
        
        Args:
            agent_factory: Agent 工厂函数
        """
        self.agent_factory = agent_factory
    
    async def execute(
        self,
        job_id: str,
        job_name: str,
        metadata: Dict[str, Any]
    ) -> str:
        """执行 Agent 任务"""
        try:
            agent = self.agent_factory()
            
            prompt = metadata.get("prompt", f"Execute task: {job_name}")
            
            state = await agent.reply(prompt)
            
            last_msg = state.messages[-1] if state.messages else {}
            content = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)
            
            return f"Completed: {content[:200]}..."
        except Exception as e:
            raise SchedulerError(f"Agent task failed: {e}", "AGENT_ERROR")


def create_scheduler(
    storage_path: Optional[str] = None
) -> Scheduler:
    """创建调度器工厂函数"""
    return Scheduler(storage_path=storage_path)


def parse_cron(cron_expr: str) -> Dict[str, Any]:
    """
    解析 Cron 表达式
    
    支持格式：
    - "* * * * * *" (秒 分 时 日 月 周)
    - "@every 1h" (每间隔)
    - "@once" (一次性)
    """
    if cron_expr.startswith("@"):
        if cron_expr == "@once":
            return {"type": "once"}
        elif cron_expr.startswith("@every "):
            interval = cron_expr[7:]
            return {"type": "interval", "interval": interval}
        elif cron_expr == "@hourly":
            return {"type": "interval", "interval": "1h"}
        elif cron_expr == "@daily":
            return {"type": "interval", "interval": "1d"}
        elif cron_expr == "@weekly":
            return {"type": "interval", "interval": "1w"}
        elif cron_expr == "@monthly":
            return {"type": "interval", "interval": "1M"}
        elif cron_expr == "@yearly":
            return {"type": "interval", "interval": "1y"}
    
    parts = cron_expr.split()
    
    if len(parts) == 5:
        return {"type": "standard", "parts": ["0"] + parts}
    elif len(parts) == 6:
        return {"type": "standard", "parts": parts}
    else:
        raise SchedulerError(f"Invalid cron expression: {cron_expr}", "CRON_PARSE_ERROR")
