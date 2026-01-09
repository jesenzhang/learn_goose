"""
API Routes Module - FastAPI endpoints for agent interaction.

This module provides:
- Chat streaming endpoints
- Session management
- State retrieval
- Approval handling
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.events import EventManager, Event
from ..core.state import AgentState
from ..db import get_db
from ..core.agent import MicroAgent

logger = logging.getLogger(__name__)


# Request/Response Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User message to send to agent")


class ApprovalRequest(BaseModel):
    """Request model for approval endpoint."""
    approved: bool = Field(..., description="Whether the action is approved")
    feedback: Optional[str] = Field(default="", description="Optional feedback for rejection")


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


async def event_generator(
    session_id: str,
    input_text: Optional[str] = None,
    resume: bool = False,
    approval_data: Optional[ApprovalRequest] = None
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for agent execution.

    Args:
        session_id: Session identifier
        input_text: Optional user input
        resume: Whether resuming from approval
        approval_data: Approval decision if resuming

    Yields:
        JSON-formatted event strings
    """
    agent = get_agent()
    db = get_db()

    # Create event queue
    q: asyncio.Queue = asyncio.Queue()

    async def listener(event: Event):
        await q.put(event)

    # Subscribe to events
    unsubscribe = agent.events.subscribe(listener, weak=True)

    # Start agent task
    task = asyncio.create_task(
        agent.run_task(
            session_id,
            user_input=input_text,
            resume=resume,
            approval_data=approval_data.model_dump() if approval_data else None
        )
    )

    try:
        while True:
            try:
                # Wait for event with short timeout
                event = await asyncio.wait_for(q.get(), timeout=0.05)
                yield json.dumps(event.model_dump(), ensure_ascii=False) + "\n"
                q.task_done()
                continue
            except asyncio.TimeoutError:
                pass

            # Exit if queue empty and task done
            if q.empty() and task.done():
                if task.exception():
                    error = task.exception()
                    logger.error(f"Task failed: {error}", exc_info=error)
                    yield json.dumps({
                        "type": "error",
                        "data": str(error)
                    }, ensure_ascii=False) + "\n"
                else:
                    logger.debug(f"Task completed for session {session_id}")
                break

            await asyncio.sleep(0.01)

    except Exception as e:
        logger.error(f"Generator error: {e}", exc_info=e)
        yield json.dumps({
            "type": "error",
            "data": str(e)
        }, ensure_ascii=False) + "\n"

    finally:
        # Cleanup
        unsubscribe()
        if not task.done():
            task.cancel()


def create_router() -> APIRouter:
    """Create and configure the API router."""
    router = APIRouter()

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "skill-micro-agent"}

    @router.get("/sessions")
    async def list_sessions():
        """
        List all sessions with metadata.

        Returns sessions sorted by last activity, newest first.
        """
        try:
            db = get_db()
            sessions = db.list_sessions()
            return {"sessions": sessions}
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/agent/{session_id}/state")
    async def get_session_state(session_id: str):
        """
        Get complete state for a session.

        Args:
            session_id: Session identifier

        Returns:
            Full agent state including history, plan, intent
        """
        try:
            db = get_db()
            state = db.load_state(session_id)
            if not state:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            return state.model_dump()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get state for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/agent/{session_id}/memories")
    async def get_session_memories(session_id: str):
        """
        Get memories for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of memories (shared memory contents)
        """
        try:
            db = get_db()
            state = db.load_state(session_id)
            if not state:
                return []

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
    async def delete_session(session_id: str):
        """
        Delete/reset a session.

        Args:
            session_id: Session identifier

        Returns:
            Success confirmation
        """
        try:
            db = get_db()
            success = db.delete_session(session_id)
            if not success:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            return {"status": "success", "msg": "Session deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/{session_id}")
    async def chat(session_id: str, req: ChatRequest):
        """
        Send a message to the agent and get streaming response.

        Args:
            session_id: Session identifier
            req: Chat request with user message

        Returns:
            Streaming response with events
        """
        return StreamingResponse(
            event_generator(session_id, input_text=req.message),
            media_type="application/x-ndjson"
        )

    @router.post("/agent/{session_id}/approval")
    async def handle_approval(session_id: str, req: ApprovalRequest):
        """
        Handle approval for a pending tool call.

        Args:
            session_id: Session identifier
            req: Approval decision

        Returns:
            Streaming response with continuation events
        """
        logger.info(f"Approval received for {session_id}: {req.approved}")
        return StreamingResponse(
            event_generator(session_id, resume=True, approval_data=req),
            media_type="application/x-ndjson"
        )

    @router.post("/approve/{session_id}")
    async def quick_approve(session_id: str):
        """
        Quick approve without feedback (auto-approve pending action).

        Args:
            session_id: Session identifier

        Returns:
            Streaming response with continuation events
        """
        approval = ApprovalRequest(approved=True, feedback="")
        return StreamingResponse(
            event_generator(session_id, resume=True, approval_data=approval),
            media_type="application/x-ndjson"
        )

    return router
