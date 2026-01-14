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

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Header
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
    file_path : Optional[str] = None
    server_type : Optional[str] = 'show'
    page_content: Optional[Dict[str,Any]] = None
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
    session_id: int,
    input_data: Optional[Dict] = None,
    resume: bool = False,
    approval_data: Optional[ApprovalRequest] = None,
    user_id: Optional[int] = None,
    format: str = "ndjson"
) -> AsyncGenerator[str, None]:
    """
    Generate events for agent execution in NDJSON or SSE format.

    Args:
        session_id: Session identifier
        input_text: Optional user input
        resume: Whether resuming from approval
        approval_data: Approval decision if resuming
        user_id: User identifier for multi-user support
        format: Response format - "ndjson" (default) or "sse"

    Yields:
        NDJSON: JSON-formatted event strings with newline
        SSE: SSE-formatted strings with data: prefix and double newline
    """
    
    # 1. 设置上下文
    try:
        agent = get_agent()
        db = get_db()
        q: asyncio.Queue = asyncio.Queue()
        async def listener(event: Event):
            await q.put(event)

        # Subscribe to events
        unsubscribe = agent.events.subscribe(listener, weak=True)

        # Start agent task
        task = asyncio.create_task(
            agent.run_task(
                session_id,
                input_data=input_data,
                resume=resume,
                approval_data=approval_data.model_dump() if approval_data else None,
                user_id=user_id
            )
        )

        while True:
            try:
                # Wait for event with short timeout
                event = await asyncio.wait_for(q.get(), timeout=0.05)
                event_data = event.model_dump(mode='json')
                # 获取事件类型
                evt_type = event_data.get("type")
                
                if format == "sse":
                    # SSE format: data: {...}\n\n
                    yield _format_sse(event_data, evt_type)
                else:
                    # NDJSON format (default): {...}\n
                    yield json.dumps(event_data, ensure_ascii=False) + "\n"

                q.task_done()
                continue
            except asyncio.TimeoutError:
                logger.debug("Timeout waiting for event")

            # Exit if queue empty and task done
            if q.empty() and task.done():
                if task.exception():
                    error = task.exception()
                    logger.error(f"Task failed: {error}", exc_info=error)
                    error_data = {"type": "error", "data": str(error)}
                    if format == "sse":
                        yield _format_sse(error_data, "error")
                    else:
                        yield json.dumps(error_data, ensure_ascii=False) + "\n"
                else:
                    logger.debug(f"Task completed for session {session_id}")
                    # Send end event for SSE
                    if format == "sse":
                        yield _format_sse({"type": "done", "data": "[DONE]"}, "done")
                break

            await asyncio.sleep(0.01)

    except Exception as e:
        logger.error(f"Generator error: {e}", exc_info=e)
        error_data = {"type": "error", "data": str(e)}
        if format == "sse":
            yield _format_sse(error_data, "error")
        else:
            yield json.dumps(error_data, ensure_ascii=False) + "\n"

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

    
    
    @router.post("/chat/{session_id}")
    async def chat(
        session_id: int,
        req: ChatRequest,
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'")
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
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(session_id, input_data=req.model_dump(), format=format),
            media_type=media_type
        )

    @router.post("/agent/{session_id}/approval")
    async def handle_approval(
        session_id: int,
        req: ApprovalRequest,
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'")
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
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(session_id, resume=True, approval_data=req, format=format),
            media_type=media_type
        )

    @router.post("/approve/{session_id}")
    async def quick_approve(
        session_id: int,
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'")
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
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(session_id, resume=True, approval_data=approval, format=format),
            media_type=media_type
        )

    # ================= Multi-User Endpoints =================

    @router.post("/users/{user_id}/chat/{session_id}")
    async def chat_for_user(
        user_id: int,
        session_id: int,
        req: ChatRequest,
        format: str = Query(default="ndjson", description="Response format: 'ndjson' or 'sse'")
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
        media_type = "text/event-stream" if format == "sse" else "application/x-ndjson"
        return StreamingResponse(
            event_generator(session_id,input_data=req.model_dump(), user_id=user_id, format=format),
            media_type=media_type
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
    async def get_artifact(session_id: int, artifact_id: str):
        """
        Get artifact data by ID.

        Args:
            session_id: Session identifier
            artifact_id: Artifact identifier

        Returns:
            Artifact data
        """
        from ..core.artifact_storage import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            data = await artifact_mgr.load(
                session_id=session_id,
                artifact_id=artifact_id,
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
    async def list_artifacts(session_id: int):
        """
        List all artifacts for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of artifact references
        """
        from ..core.artifact_storage import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            refs = await artifact_mgr.list_all(session_id=session_id)

            return {
                "session_id": session_id,
                "artifacts": [
                    {
                        "id": ref.id,
                        "type": ref.type,
                        "text": ref.text,
                        "size": ref.size,
                        "storage_type": ref.storage_type.value,
                        "created_at": ref.created_at,
                    }
                    for ref in refs
                ],
            }
        except Exception as e:
            logger.error(f"Failed to list artifacts for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sessions/{session_id}/artifacts/stats")
    async def get_artifact_stats(session_id: int):
        """
        Get artifact statistics for a session.

        Args:
            session_id: Session identifier

        Returns:
            Artifact statistics
        """
        from ..core.artifact_storage import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            stats = await artifact_mgr.get_stats(session_id=session_id)
            return stats
        except Exception as e:
            logger.error(f"Failed to get artifact stats for {session_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/sessions/{session_id}/artifacts/{artifact_id}")
    async def delete_artifact(session_id: int, artifact_id: str):
        """
        Delete an artifact by ID.

        Args:
            session_id: Session identifier
            artifact_id: Artifact identifier

        Returns:
            Deletion confirmation
        """
        from ..core.artifact_storage import get_manager

        artifact_mgr = get_manager()
        if artifact_mgr is None:
            raise HTTPException(status_code=503, detail="Artifact manager not available")

        try:
            success = await artifact_mgr.delete(
                session_id=session_id,
                artifact_id=artifact_id,
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
        from ..core.artifact_storage import get_manager

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
        from ..core.artifact_storage import get_manager

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


