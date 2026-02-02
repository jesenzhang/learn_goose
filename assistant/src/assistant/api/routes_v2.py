"""
API Routes Module - V2 FastAPI endpoints for agent interaction.

This module provides:
- Chat streaming endpoints
- Approval handling
- Resume/reconnect support
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..events.event_wrapper import Event
from ..core.state import AgentState
from ..db import get_db
from ..core.V2 import MicroAgentV2

logger = logging.getLogger(__name__)


# Request/Response Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User message to send to agent")
    file_path: Optional[str] = None
    server_type: Optional[str] = "show"
    page_content: Optional[str] = None
    deep_thinking: Optional[bool] = False
    is_deep_research: Optional[bool] = False


class ApprovalRequest(BaseModel):
    """Request model for approval endpoint."""
    approved: bool = Field(..., description="Whether the action is approved")
    feedback: Optional[str] = Field(default="", description="Optional feedback for rejection")


# Global agent instance (set by main.py)
_agent_v2: Optional[MicroAgentV2] = None


def set_agent_v2(agent: MicroAgentV2):
    """Set the global agent instance."""
    global _agent_v2
    _agent_v2 = agent


def get_agent_v2() -> MicroAgentV2:
    """Get the global agent instance."""
    if _agent_v2 is None:
        raise RuntimeError("V2 Agent not initialized")
    return _agent_v2


def _generate_run_id(session_id: int) -> str:
    return f"{session_id}:{int(time.time() * 1000)}:{uuid.uuid4().hex[:8]}"


async def get_agent_state(session_id: int) -> AgentState:
    db = get_db()
    data = await db.load_state(session_id)
    return AgentState(**data) if data else AgentState(session_id=session_id)


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
    heart_beat: float = 15.0,
) -> AsyncGenerator[str, None]:
    agent = get_agent_v2()
    if user_id is None:
        user_id = state.user_id
    q: asyncio.Queue = asyncio.Queue()

    handle = await agent.run_task(
        state,
        run_id,
        input_data=input_data,
        resume=resume,
        approval_data=approval_data.model_dump() if approval_data else None,
        user_id=user_id,
    )

    current_task_id = run_id

    async def streamer_to_queue():
        try:
            streamer = agent.get_streamer(session_id, current_task_id)
            subscription = streamer.bus.subscribe(current_task_id, after_seq_id=last_event_id)

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

            if hasattr(handle, "start"):
                handle.start()
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

    streamer_task = asyncio.create_task(streamer_to_queue())
    last_activity_time = time.time()

    try:
        while True:
            handle = agent.get_task_handle(session_id)
            try:
                event = await asyncio.wait_for(q.get(), timeout=1.0)
                event_data = event.model_dump(mode="json")
                if format == "sse":
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                else:
                    yield json.dumps(event_data, ensure_ascii=False) + "\n"
                last_activity_time = time.time()
                q.task_done()
            except asyncio.TimeoutError:
                if q.empty() and (handle is None or not handle.is_running):
                    if handle and handle.is_failed:
                        err_msg = str(handle.get_exception())
                        yield _format_error_event(err_msg, format)
                    break
                if (time.time() - last_activity_time) >= heart_beat:
                    yield ": keep-alive\n\n" if format == "sse" else '{"type":"ping"}\n'
                    last_activity_time = time.time()
    finally:
        if not streamer_task.done():
            streamer_task.cancel()
        logger.info(f"Stream connection closed for session {session_id}")


def create_router_v2() -> APIRouter:
    router = APIRouter(prefix="/api/v2")
    STREAMING_HEADERS = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Encoding": "none",
    }

    @router.post("/chat")
    async def chat(
        req: ChatRequest,
        session_id: int = Query(description="Session identifier"),
        resume: bool = Query(default=False, description="Resume flag"),
        run_id: Optional[str] = Query(default=None, description="Run identifier (required for resume)"),
        last_event_id: int = Query(default=-1, description="Last event ID for resuming"),
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'"),
        state: AgentState = Depends(get_agent_state),
    ):
        logger.info(
            "V2 chat request params: session_id=%s resume=%s last_event_id=%s format=%s body=%s",
            session_id,
            resume,
            last_event_id,
            format,
            req.model_dump(),
        )
        if resume:
            run_id = _resolve_run_id_for_resume(state, run_id)
            if not run_id:
                raise HTTPException(status_code=400, detail="run_id is required when resume=true")
        else:
            if not run_id:
                run_id = _generate_run_id(session_id)
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
                resume=resume,
                last_event_id=last_event_id,
                input_data=req.model_dump(),
                format=format,
            ),
            media_type=media_type,
            headers=STREAMING_HEADERS,
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
        logger.info(f"V2 approval received for {session_id}: {req.approved}")
        run_id = _resolve_run_id_for_resume(state, run_id)
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required for approval")
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
                approval_data=req,
                format=format,
            ),
            media_type=media_type,
            headers=STREAMING_HEADERS,
        )

    @router.post("/approve/{session_id}")
    async def quick_approve(
        session_id: int,
        run_id: Optional[str] = Query(default=None, description="Run identifier (required)"),
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'"),
        state: AgentState = Depends(get_agent_state),
    ):
        approval = ApprovalRequest(approved=True, feedback="")
        run_id = _resolve_run_id_for_resume(state, run_id)
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required for approval")
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
                approval_data=approval,
                format=format,
            ),
            media_type=media_type,
            headers=STREAMING_HEADERS,
        )

    return router
