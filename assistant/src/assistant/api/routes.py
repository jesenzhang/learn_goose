"""
API Routes Module - FastAPI endpoints for agent interaction.

This module provides:
- Chat streaming endpoints
- Session management
- State retrieval
- Approval handling
- Authentication endpoints
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, AsyncGenerator
import time
import uuid

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Header, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic.v1.types import NoneStrBytes

from ..core.events import EventType
from ..events.event_wrapper import Event
from ..core.state import AgentState
from ..db import get_db
from ..core import MicroAgent

logger = logging.getLogger(__name__)


# Request/Response Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User message to send to agent")
    file_path : Optional[str] = None
    server_type : Optional[str] = 'show'
    page_content: Optional[str] = None
    deep_thinking: Optional[bool] = False
    is_deep_research: Optional[bool] = False

class ApprovalRequest(BaseModel):
    """Request model for approval endpoint."""
    approved: bool = Field(..., description="Whether the action is approved")
    feedback: Optional[str] = Field(default="", description="Optional feedback for rejection")


# Auth Models
class LoginRequest(BaseModel):
    """Request model for login endpoint."""
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")

class RegisterRequest(BaseModel):
    """Request model for registration endpoint."""
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    display_name: Optional[str] = Field(default=None, description="Display name")
    email: Optional[str] = Field(default=None, description="Email address")

class ValidateTokenRequest(BaseModel):
    """Request model for token validation."""
    token: str = Field(..., description="Authentication token")


# Global agent instance (set by main.py)
_agent: Optional[MicroAgent] = None


def set_agent(agent: MicroAgent):
    """Set the global agent instance."""
    global _agent
    _agent = agent


def get_agent() -> MicroAgent:
    """Get the global agent instance."""
    if _agent is None:
        raise RuntimeError("Agent not initialized")
    return _agent


def _generate_run_id(session_id: int) -> str:
    return f"{session_id}:{int(time.time() * 1000)}:{uuid.uuid4().hex[:8]}"


async def get_agent_state(session_id: int) -> AgentState:
    db = get_db()
    data = await db.load_state(session_id)
    return AgentState(**data) if data else AgentState(session_id=session_id)


def _format_sse(data: Dict[str, Any], event_type: Optional[str] = None) -> str:
    """
    Format event data as Standard Server-Sent Events (SSE).
    Format:
        event: <event_type>
        data: <json_payload>
        <newline>
    """
    buffer = ""
    # 1. 添加 event 字段 (如果存在)
    # 这允许客户端直接通过 event listener 区分消息类型
    if event_type:
        buffer += f"event: {event_type}\n"
    
    # 2. 添加 data 字段
    # 为了保持与 NDJSON 逻辑的一致性（客户端 process_stream 里通过 data.get("data") 取值），
    # 我们仍然把完整的 data 字典（包含 type）发过去，或者你也可以只发 payload。
    # 这里为了兼容性，发送完整的 data 字典。
    buffer += f"data: {json.dumps(data, ensure_ascii=False)}\n"
    
    # 3. 消息结束符 (双换行)
    buffer += "\n"
    return buffer

async def event_generator(
        state: AgentState,
        run_id: str,
        session_id: int,
        last_event_id: Optional[int] = -1,
        input_data: Optional[Dict] = None,
        resume: bool = False,
        approval_data: Optional[ApprovalRequest] = None,
        user_id: Optional[int] = None,
        format: str = "ndjson",
        heart_beat: float = 15.0
    ) -> AsyncGenerator[str, None]:
    
    agent = get_agent()
    db = get_db()
    if user_id is None:
        user_id = state.user_id
    q: asyncio.Queue = asyncio.Queue()
    # --- 1. 触发任务并获取句柄 ---
    # 我们先调用 run_task。根据你之前的实现，它会立即返回一个 handle
    # handle 里包含了本次生成的 run_id (即 task_id)
    handle = await agent.run_task(
        state,
        run_id,
        input_data=input_data,
        resume=resume,
        approval_data=approval_data.model_dump() if approval_data else None,
        user_id=user_id
    )
    
    current_task_id = run_id  # 获取本次任务的唯一 ID

    # --- 1. 定义监听器 (必须在启动任务前或同时准备好) ---
    async def streamer_to_queue():
        try:
            streamer = agent.get_streamer(session_id, current_task_id)
            # Prepare live subscription first to avoid gaps.
            subscription = streamer.bus.subscribe(current_task_id, after_seq_id=last_event_id)

            # Replay history when resuming from a specific seq_id.
            last_seq_id = last_event_id
            if last_event_id is not None and last_event_id >= 0:
                from ..events import EventReplayManager, ReplayMode

                replay_cfg = agent.current_generation.config.events if agent.current_generation else None
                replay_mgr = EventReplayManager(
                    agent._store,
                    cache_size=getattr(replay_cfg, "replay_cache_size", None),
                    batch_size=getattr(replay_cfg, "replay_batch_size", None),
                )
                replay_queue = await replay_mgr.start_replay(
                    session_id=str(session_id),
                    mode=ReplayMode.REPLAY,
                    run_id=current_task_id,
                    after_seq_id=last_event_id,
                )

                while True:
                    replay_event = await replay_queue.get()
                    if not isinstance(replay_event, dict):
                        continue
                    replay_type = replay_event.get("type")
                    if replay_type in {"replay_complete", "replay_error", "replay_stopped"}:
                        break
                    meta = {
                        "run_id": replay_event.get("run_id"),
                        "seq_id": replay_event.get("seq_id"),
                        "session_id": replay_event.get("session_id"),
                        "parent_run_id": replay_event.get("parent_run_id"),
                        **(replay_event.get("metadata") or {}),
                    }
                    event = Event(
                        id=replay_event.get("id"),
                        type=replay_event.get("type"),
                        data=replay_event.get("data"),
                        timestamp=replay_event.get("timestamp"),
                        meta=meta,
                    )
                    if isinstance(meta.get("seq_id"), int):
                        last_seq_id = max(last_seq_id, meta["seq_id"])
                    await q.put(event)
            if hasattr(handle, 'start'):
                handle.start() # 这一步会执行 start_signal.set()
            else:
                # 如果你没在 handle 封装，可以直接在 agent 层处理
                # 视你之前的具体实现而定
                pass
            mismatch_logged = False
            async for streamer_event in subscription:
                if streamer_event.run_id != current_task_id:
                    if not mismatch_logged:
                        logger.error(
                            "Stream run_id mismatch detected: expected=%s actual=%s session_id=%s",
                            current_task_id,
                            streamer_event.run_id,
                            session_id,
                        )
                        mismatch_logged = True
                    continue
                if last_seq_id is not None and streamer_event.seq_id <= last_seq_id:
                    continue
                event = Event.from_streamer_event(streamer_event)
                last_seq_id = max(last_seq_id, streamer_event.seq_id)
                
                await q.put(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Streamer Error: {e}")

    # 启动监听后台任务
    streamer_task = asyncio.create_task(streamer_to_queue())
    
    # --- 3. 消费循环 (并行处理队列消息) ---
    last_activity_time = time.time()
    
    last_saved_seq_id = state.last_delivered_seq_id or -1
    last_save_ts = time.time()

    async def _schedule_state_save():
        try:
            await db.save_state(session_id, state.model_dump(exclude_none=True))
        except Exception as e:
            logger.warning(f"Failed to save state for last_delivered_seq_id: {e}")

    try:
        while True:
            # 动态检查任务句柄状态
            handle = agent.get_task_handle(session_id)
            
            try:
                # 缩短超时时间，以便频繁检查 handle 状态
                event = await asyncio.wait_for(q.get(), timeout=1.0)
                
                # 转换并发送
                event_data = event.model_dump(mode='json')
                if format == "sse":
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                else:
                    yield json.dumps(event_data, ensure_ascii=False) + "\n"

                # Track last delivered seq_id for reconnect safety.
                meta = event.meta or {}
                seq_id = meta.get("seq_id")
                run_id = meta.get("run_id")
                if isinstance(seq_id, int) and run_id:
                    state.last_delivered_seq_id = seq_id
                    state.last_delivered_run_id = str(run_id)
                    now = time.time()
                    if (seq_id - last_saved_seq_id) >= 20 or (now - last_save_ts) >= 2.0:
                        last_saved_seq_id = seq_id
                        last_save_ts = now
                        asyncio.create_task(_schedule_state_save())
                
                last_activity_time = time.time()
                q.task_done()

            except asyncio.TimeoutError:
                # 检查任务是否已经结束 (包括正常结束、崩溃、或者进入了等待审批的 return)
                # 如果 handle 为 None 且队列空了，说明任务执行体已经退出
                if q.empty() and (handle is None or not handle.is_running):
                    # 如果是因为报错结束的，可以最后补发一个错误事件
                    if handle and handle.is_failed:
                        err_msg = str(handle.get_exception())
                        yield _format_error_event(err_msg, format)
                    break

                # 心跳检查
                if (time.time() - last_activity_time) >= heart_beat:
                    yield ": keep-alive\n\n" if format == "sse" else '{"type":"ping"}\n'
                    last_activity_time = time.time()

    finally:
        # 清理工作
        if not streamer_task.done():
            streamer_task.cancel()
        # 注意：不要 cancel agent_trigger_task，除非你希望用户一关网页 Agent 就停止工作
        logger.info(f"Stream connection closed for session {session_id}")

def _format_error_event(msg: str, format: str) -> str:
    data = {"type": "error", "data": msg}
    return (
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        if format == "sse"
        else json.dumps(data, ensure_ascii=False) + "\n"
    )


def _validate_request_identity(
    *,
    state: AgentState,
    session_id: int,
    run_id: Optional[str],
    user_id: Optional[int],
) -> None:
    if state.session_id != session_id:
        logger.error(
            "Session mismatch detected: req.session_id=%s state.session_id=%s run_id=%s user_id=%s state.user_id=%s",
            session_id,
            state.session_id,
            run_id,
            user_id,
            state.user_id,
        )
        raise HTTPException(status_code=409, detail="session_id mismatch")
    if user_id is not None and state.user_id is not None and user_id != state.user_id:
        logger.error(
            "User mismatch detected: req.user_id=%s state.user_id=%s session_id=%s run_id=%s",
            user_id,
            state.user_id,
            session_id,
            run_id,
        )
        raise HTTPException(status_code=403, detail="user_id mismatch")
    if run_id and ":" in run_id:
        prefix = run_id.split(":", 1)[0]
        if prefix.isdigit() and int(prefix) != session_id:
            logger.error(
                "RunId mismatch detected: run_id=%s session_id=%s state.session_id=%s",
                run_id,
                session_id,
                state.session_id,
            )
            raise HTTPException(status_code=409, detail="run_id mismatch")


def _resolve_run_id_for_resume(state: AgentState, run_id: Optional[str]) -> Optional[str]:
    if run_id:
        return run_id
    if state.pending_run_id:
        return state.pending_run_id
    if state.active_run_id:
        return state.active_run_id
    if state.last_run_id:
        return state.last_run_id
    return None


def create_router() -> APIRouter:
    """Create and configure the API router."""
    router = APIRouter(prefix="/api/v1")
    # 常量定义
    STREAMING_HEADERS = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Encoding": "none"
    }

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "skill-micro-agent"}

    @router.get("/skills")
    async def list_skills():
        """
        List all available skills with their labels and metadata.

        Returns:
            List of skills with name, label (Chinese display name), description, and type
        """
        try:
            agent = get_agent()
            gen = agent.current_generation
            if not gen or not gen.skill_loader:
                return {"skills": []}

            skills_info = []
            for skill_name, skill in gen.skill_loader._skills.items():
                skills_info.append({
                    "name": skill_name,
                    "label": skill.label or skill_name,  # 如果没有 label，使用 name 作为 fallback
                    "description": skill.description,
                    "type": skill.skill_type.value,
                    "tools": [
                        {
                            "name": tool.name,
                            "label": tool.label or tool.name,
                            "description": tool.description,
                            "is_sensitive": tool.is_sensitive
                        }
                        for tool in skill.get_tools()
                    ]
                })
            return {"skills": skills_info}
        except Exception as e:
            logger.error(f"Failed to list skills: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/session/{session_title}")
    async def create_session(session_title: str):
        """
        Create a new session.
        """
        try:
            db = get_db()   
            session_id = await db.create_session(session_title)
            return {"status": "success", "msg": "Session created", "session_id": session_id}
        except Exception as e:
            logger.error(f"Failed to create session {session_title}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))
        
    @router.get("/sessions")
    async def list_sessions():
        """
        List all sessions with metadata.

        Returns sessions sorted by last activity, newest first.
        """
        try:
            db = get_db()
            sessions = await db.list_sessions()
            return {"sessions": sessions}
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/agent/{session_id}/state")
    async def get_session_state(session_id: int):
        """
        Get complete state for a session.

        Args:
            session_id: Session identifier

        Returns:
            Full agent state including history, plan, intent
        """
        try:
            db = get_db()
            state_data = await db.load_state(session_id)
            if not state_data:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            # Convert dict to AgentState for consistent response
            state = AgentState(**state_data)
            return state.model_dump()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get state for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/agent/{session_id}/memories")
    async def get_session_memories(session_id: int):
        """
        Get memories for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of memories (shared memory contents)
        """
        try:
            db = get_db()
            state_data = await db.load_state(session_id)
            if not state_data:
                return []

            state = AgentState(**state_data)
            memories = []
            for key, val in state.shared_memory.items():
                preview = str(val)[:100] + "..." if len(str(val)) > 100 else str(val)
                memories.append({
                    "content": f"**{key}**: {preview}",
                    "key": key
                })
            return memories
        except Exception as e:
            logger.error(f"Failed to get memories for {session_id}: {e}", exc_info=e)
            return []

    @router.delete("/agent/{session_id}")
    async def delete_session(session_id: int):
        """
        Delete/reset a session.

        Args:
            session_id: Session identifier

        Returns:
            Success confirmation
        """
        try:
            db = get_db()
            success = await db.delete_state(session_id)
            if not success:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            return {"status": "success", "msg": "Session deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/agent/cancel")
    async def cancel_task(session_id: int = Query(description="Session identifier"),):
        """
        Cancel a running task for a session.

        Args:
            session_id: Session identifier

        Returns:
            Cancellation confirmation
        """
        try:
            agent = get_agent()
            success = await agent.cancel_task(session_id)
            if not success:
                raise HTTPException(status_code=400, detail=f"Task for session {session_id} could not be cancelled (not running or not found)")
            return {"status": "success", "msg": "Task cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel task for session {session_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat")
    async def chat(
        req: ChatRequest,
        session_id: int = Query(description="Session identifier"),
        resume: Optional[bool]= Query(default=False, description="Resume flag"),
        run_id: Optional[str] = Query(default=None, description="Run identifier (required for resume)"),
        last_seq_id: Optional[int] = Query(default=-1, description="Last event ID for resuming"),
        format: Optional[str] = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'"),
        state: AgentState = Depends(get_agent_state),
    ):
        """
        Send a message to the agent and get streaming response.

        Args:
            session_id: Session identifier
            req: Chat request with user message
            format: Response format - 'ndjson' (default) or 'sse'

        Returns:
            Streaming response with events in NDJSON or SSE format
        """
        
        logger.info(
            "Chat request params: session_id=%s resume=%s last_seq_id=%s format=%s body=%s",
            session_id,
            resume,
            last_seq_id,
            format,
            req.model_dump(),
        )
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        if resume:
            run_id = _resolve_run_id_for_resume(state, run_id)
            if not run_id:
                raise HTTPException(status_code=400, detail="run_id is required when resume=true")
            if last_seq_id == -1 and state.last_delivered_run_id == run_id and state.last_delivered_seq_id is not None:
                last_seq_id = state.last_delivered_seq_id
        else:
            if not run_id:
                run_id = _generate_run_id(session_id)
        _validate_request_identity(
            state=state,
            session_id=session_id,
            run_id=run_id,
            user_id=state.user_id,
        )
        return StreamingResponse(
            event_generator(state, run_id, session_id, resume=resume, last_event_id=last_seq_id, input_data=req.model_dump(), format=format),
            media_type=media_type,
            headers=STREAMING_HEADERS
        )
        
    @router.post("/agent/{session_id}/approval")
    async def handle_approval(
        session_id: int,
        req: ApprovalRequest,
        run_id: Optional[str] = Query(default=None, description="Run identifier (required)"),
        last_event_id: int = Query(default=-1, description="Last event ID for resuming"),
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'"),
        state: AgentState = Depends(get_agent_state),
    ):
        """
        Handle approval for a pending tool call.

        Args:
            session_id: Session identifier
            req: Approval decision
            format: Response format - 'ndjson' (default) or 'sse'

        Returns:
            Streaming response with continuation events
        """
        logger.info(f"Approval received for {session_id}: {req.approved}")
        run_id = _resolve_run_id_for_resume(state, run_id)
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required for approval")
        if last_event_id == -1 and state.last_delivered_run_id == run_id and state.last_delivered_seq_id is not None:
            last_event_id = state.last_delivered_seq_id
        _validate_request_identity(
            state=state,
            session_id=session_id,
            run_id=run_id,
            user_id=state.user_id,
        )
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(state, run_id, session_id, resume=True, last_event_id=last_event_id, approval_data=req, format=format),
            media_type=media_type,
            headers=STREAMING_HEADERS
        )

    @router.post("/approve/{session_id}")
    async def quick_approve(
        session_id: int,
        run_id: Optional[str] = Query(default=None, description="Run identifier (required)"),
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'"),
        state: AgentState = Depends(get_agent_state),
    ):
        """
        Quick approve without feedback (auto-approve pending action).

        Args:
            session_id: Session identifier
            format: Response format - 'ndjson' (default) or 'sse'

        Returns:
            Streaming response with continuation events
        """
        approval = ApprovalRequest(approved=True, feedback="")
        last_event_id = -1
        run_id = _resolve_run_id_for_resume(state, run_id)
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required for approval")
        if state.last_delivered_run_id == run_id and state.last_delivered_seq_id is not None:
            # Quick-approve has no last_event_id parameter; use stored seq id to avoid full replay.
            last_event_id = state.last_delivered_seq_id
        _validate_request_identity(
            state=state,
            session_id=session_id,
            run_id=run_id,
            user_id=state.user_id,
        )
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(
                state,
                run_id,
                session_id,
                resume=True,
                last_event_id=last_event_id,
                approval_data=approval,
                format=format,
            ),
            media_type=media_type,
            headers=STREAMING_HEADERS
        )

    # ================= Multi-User Endpoints =================

    @router.post("/users/{user_id}/chat/{session_id}")
    async def chat_for_user(
        user_id: int,
        session_id: int,
        req: ChatRequest,
        run_id: Optional[str] = Query(default=None, description="Run identifier"),
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'"),
        state: AgentState = Depends(get_agent_state),
    ):
        """
        Send a message to agent for a specific user and get streaming response.

        Args:
            user_id: User identifier
            session_id: Session identifier
            req: Chat request with user message
            format: Response format - 'ndjson' (default) or 'sse'

        Returns:
            Streaming response with events in NDJSON or SSE format
        """
        if not run_id:
            run_id = _generate_run_id(session_id)
        _validate_request_identity(
            state=state,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
        )
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(state, run_id, session_id, input_data=req.model_dump(), user_id=user_id, format=format),
            media_type=media_type,
            headers=STREAMING_HEADERS
        )

    @router.get("/users/{user_id}/sessions")
    async def list_user_sessions(user_id: int, limit: Optional[int] = None):
        """
        List all sessions for a specific user.

        Args:
            user_id: User identifier
            limit: Optional limit on number of sessions to return

        Returns:
            List of user sessions with metadata
        """
        try:
            db = get_db()
            if hasattr(db, 'list_sessions_for_user'):
                sessions = await db.list_sessions_for_user(user_id, limit)
            else:
                all_sessions = await db.list_sessions()
                sessions = [s for s in all_sessions if s.get('user_id') == user_id]
                if limit:
                    sessions = sessions[:limit]
            return {"sessions": sessions}
        except Exception as e:
            logger.error(f"Failed to list sessions for user {user_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/users/{user_id}/stats")
    async def get_user_statistics(user_id: int):
        """
        Get statistics for a specific user.

        Args:
            user_id: User identifier

        Returns:
            User statistics including sessions, events, and memories count
        """
        try:
            db = get_db()
            if hasattr(db, 'get_user_stats'):
                stats = await db.get_user_stats(user_id)
            else:
                all_sessions = await db.list_sessions()
                user_sessions = [s for s in all_sessions if s.get('user_id') == user_id]
                stats = {
                    "user_id": user_id,
                    "sessions": len(user_sessions),
                    "events": 0,
                    "memories": 0
                }
            return stats
        except Exception as e:
            logger.error(f"Failed to get stats for user {user_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/users/{user_id}")
    async def delete_user_data(user_id: int):
        """
        Delete all data for a specific user.

        Args:
            user_id: User identifier

        Returns:
            Success confirmation with count of deleted sessions
        """
        try:
            db = get_db()
            if hasattr(db, 'delete_user_sessions'):
                count = await db.delete_user_sessions(user_id)
            else:
                all_sessions = await db.list_sessions()
                user_sessions = [s for s in all_sessions if s.get('user_id') == user_id]
                count = 0
                for session in user_sessions:
                    if await db.delete_state(session['id']):
                        count += 1
            return {"status": "success", "deleted_sessions": count}
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/users")
    async def list_all_users():
        """
        List all users in the system.

        Returns:
            List of users with session counts and last active timestamp
        """
        try:
            db = get_db()
            if hasattr(db, 'list_all_users'):
                users = await db.list_all_users()
            else:
                all_sessions = await db.list_sessions()
                user_map = {}
                for session in all_sessions:
                    user_id = session.get('user_id', 'default')
                    if user_id not in user_map:
                        user_map[user_id] = {
                            "user_id": user_id,
                            "session_count": 0,
                            "last_active": session.get('updated_at', 0)
                        }
                    user_map[user_id]['session_count'] += 1
                    if session.get('updated_at', 0) > user_map[user_id]['last_active']:
                        user_map[user_id]['last_active'] = session['updated_at']
                users = list(user_map.values())
                users = sorted(users, key=lambda x: x['last_active'], reverse=True)
            return {"users": users}
        except Exception as e:
            logger.error(f"Failed to list users: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    # ================= Artifact Management Endpoints =================

    @router.get("/sessions/{session_id}/artifacts/{artifact_id}")
    async def get_artifact(
        session_id: int,
        artifact_id: str,
        storage_type: Optional[str] = Query(default=None, description="Storage type hint"),
    ):
        """
        Get artifact data by ID.

        Args:
            session_id: Session identifier
            artifact_id: Artifact identifier

        Returns:
            Artifact data
        """
        from ..memory import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            data = await artifact_mgr.load(
                session_id=session_id,
                item_id=artifact_id,
                storage_type=storage_type,
            )

            if data is None:
                raise HTTPException(status_code=404, detail="Artifact not found")

            return {
                "id": artifact_id,
                "session_id": session_id,
                "data": data,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get artifact {artifact_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sessions/{session_id}/artifacts")
    async def list_artifacts(
        session_id: int,
        storage_type: Optional[str] = Query(default=None, description="Filter by storage_type"),
    ):
        """
        List all artifacts for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of artifact references
        """
        from ..memory import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            refs = await artifact_mgr.list_all(session_id=session_id, storage_type=storage_type)

            artifacts = [
                {
                    "id": ref.id,
                    "type": ref.type,
                    "text": ref.text,
                    "size": ref.size,
                    "storage_type": ref.storage_type.value,
                    "created_at": ref.created_at,
                }
                for ref in refs
            ]
            if storage_type:
                artifacts = [a for a in artifacts if a.get("storage_type") == storage_type]
            return {
                "session_id": session_id,
                "artifacts": artifacts,
            }
        except Exception as e:
            logger.error(f"Failed to list artifacts for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sessions/{session_id}/artifacts/stats")
    async def get_artifact_stats(
        session_id: int,
        storage_type: Optional[str] = Query(default=None, description="Storage type hint"),
    ):
        """
        Get artifact statistics for a session.

        Args:
            session_id: Session identifier

        Returns:
            Artifact statistics
        """
        from ..memory import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            stats = await artifact_mgr.get_stats(session_id=session_id, storage_type=storage_type)
            return stats
        except Exception as e:
            logger.error(f"Failed to get artifact stats for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/sessions/{session_id}/artifacts/{artifact_id}")
    async def delete_artifact(
        session_id: int,
        artifact_id: str,
        storage_type: Optional[str] = Query(default=None, description="Storage type hint"),
    ):
        """
        Delete an artifact by ID.

        Args:
            session_id: Session identifier
            artifact_id: Artifact identifier

        Returns:
            Deletion confirmation
        """
        from ..memory import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            success = await artifact_mgr.delete(
                session_id=session_id,
                item_id=artifact_id,
                storage_type=storage_type,
            )

            if not success:
                raise HTTPException(status_code=404, detail="Artifact not found")

            # Also remove from shared memory if it exists
            db = get_db()
            state_data = await db.load_state(session_id)
            if state_data:
                state = AgentState(**state_data)
                if artifact_id in state.shared_memory:
                    del state.shared_memory[artifact_id]
                    await db.save_state(session_id, state.model_dump())

            return {"deleted": artifact_id}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete artifact {artifact_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/sessions/{session_id}/artifacts")
    async def cleanup_session_artifacts(session_id: int):
        """
        Clean up all artifacts for a session.

        Args:
            session_id: Session identifier

        Returns:
            Cleanup confirmation with count
        """
        from ..memory import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            count = await artifact_mgr.cleanup_session(session_id=session_id)

            # Also remove from shared memory
            db = get_db()
            state_data = await db.load_state(session_id)
            if state_data:
                state = AgentState(**state_data)
                removed_count = 0
                for key in list(state.shared_memory.keys()):
                    if key.startswith("art_"):
                        del state.shared_memory[key]
                        removed_count += 1
                await db.save_state(session_id, state.model_dump())
                logger.info(f"Removed {removed_count} artifact refs from shared memory")

            return {"session_id": session_id, "cleaned": count}
        except Exception as e:
            logger.error(f"Failed to cleanup artifacts for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/artifacts/health")
    async def artifact_health_check():
        """
        Health check for artifact manager.

        Returns:
            Health status of all session storage backends
        """
        from ..memory import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            return {"status": "disabled", "message": "Artifact manager not available"}

        try:
            health = await artifact_mgr.health_check()
            return {
                "status": "ok",
                "sessions": health,
            }
        except Exception as e:
            logger.error(f"Artifact health check failed: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    return router


