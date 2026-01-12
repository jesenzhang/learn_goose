"""
Agent Routes - RESTful endpoints for multi-style agent execution.

This module provides endpoints for:
- Chat/agent execution (all 5 styles)
- Streaming responses with SSE
- Session management
- Approval handling
- Multi-user authentication and authorization
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import StreamingResponse

from pho.api.schemas import (
    ChatRequest,
    ChatResponse,
    StreamingEvent,
    SessionInfo,
    SessionListResponse,
    SessionState,
    ApprovalRequest,
    AgentStyleEnum,
    ExecutionStatusEnum,
    HealthResponse,
)
from pho.agent import (
    PhoAgent,
    AgentStyle,
    Context,
    AgentStatus,
    AgentEventType,
)
from pho.providers import ProviderFactory, ModelConfig
from pho.api.auth_middleware import get_current_user, get_required_user
from pho.auth import AuthUser

logger = logging.getLogger(__name__)


# ============================================================================
# In-Memory Session Storage (simplified, replace with DB in production)
# ============================================================================

_sessions: Dict[str, Dict[str, Any]] = {}
_session_lock = asyncio.Lock()


def _create_session(style: AgentStyle, user_id: str) -> str:
    """Create a new session with user association."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    _sessions[session_id] = {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "variables": {},
        "style": style,
        "message_count": 0,
    }
    return session_id


def _get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session data."""
    return _sessions.get(session_id)


def _update_session(session_id: str, message: str, response: str):
    """Update session with new messages."""
    if session_id in _sessions:
        session = _sessions[session_id]
        session["messages"].append({"role": "user", "content": message})
        session["messages"].append({"role": "assistant", "content": response})
        session["updated_at"] = datetime.utcnow().isoformat()
        session["message_count"] = len(session["messages"])


# ============================================================================
# Agent Instance Factory
# ============================================================================

def create_agent_instance(
    style: AgentStyle,
    llm_provider: str = "openai",
    model_name: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
) -> PhoAgent:
    """Create a PhoAgent instance with the specified style."""
    # Get API key from parameter or environment
    if not api_key:
        import os
        api_key = os.getenv("OPENAI_API_KEY", "demo-key")

    # Create LLM
    llm = ProviderFactory.create_llm(llm_provider, ModelConfig(
        model_name=model_name,
        api_key=api_key
    ))

    # Create agent
    return PhoAgent(
        style=style,
        llm=llm,
        system_prompt="You are Pho, a helpful AI assistant with access to tools.",
    )


# ============================================================================
# SSE Event Generator
# ============================================================================

async def _event_generator(
    agent: PhoAgent,
    input_text: str,
    context: Context,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for agent execution.

    Yields:
        JSON-formatted event strings
    """
    try:
        # Emit start event
        yield json.dumps({
            "type": "start",
            "data": {"input": input_text},
            "timestamp": time.time(),
        }, ensure_ascii=False) + "\n"

        # Stream agent response
        full_text = ""
        async for response in agent.engine.execute_stream(input_text, context):
            full_text += response.text or ""

            # Map AgentStatus to event type
            event_type = "text"
            if response.status == AgentStatus.THINKING:
                event_type = "thinking"
            elif response.status == AgentStatus.TOOLING:
                event_type = "tooling"
            elif response.status == AgentStatus.STREAMING:
                event_type = "text"
            elif response.status == AgentStatus.COMPLETED:
                event_type = "complete"
            elif response.status == AgentStatus.ERROR:
                event_type = "error"

            # Emit event
            event_data = {"text": response.text}
            if response.events:
                event_data["events"] = [
                    {"type": e.type.value, "data": e.data}
                    for e in response.events
                ]

            yield json.dumps({
                "type": event_type,
                "data": event_data,
                "timestamp": time.time(),
            }, ensure_ascii=False) + "\n"

        # Emit final complete event
        yield json.dumps({
            "type": "done",
            "data": {"full_text": full_text, "length": len(full_text)},
            "timestamp": time.time(),
        }, ensure_ascii=False) + "\n"

    except Exception as e:
        logger.error(f"Event generator error: {e}", exc_info=e)
        yield json.dumps({
            "type": "error",
            "data": {"error": str(e)},
            "timestamp": time.time(),
        }, ensure_ascii=False) + "\n"


# ============================================================================
# Router Creation
# ============================================================================

def create_agent_router() -> APIRouter:
    """Create and configure the agent API router."""
    router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])

    # ========================================================================
    # Health Check
    # ========================================================================

    @router.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(status="ok", version="0.1.0")

    # ========================================================================
    # Session Management
    # ========================================================================

    @router.get("/sessions", response_model=SessionListResponse)
    async def list_sessions(
        current_user: Optional[AuthUser] = Depends(get_current_user)
    ):
        """
        List sessions accessible to the current user.

        If authenticated, returns user's sessions.
        If not authenticated, returns empty list.
        """
        async with _session_lock:
            if current_user:
                # Filter sessions by user_id
                user_sessions = [
                    SessionInfo(
                        session_id=s["session_id"],
                        user_id=s.get("user_id"),
                        created_at=s["created_at"],
                        updated_at=s["updated_at"],
                        message_count=s["message_count"],
                        style=AgentStyleEnum(s["style"].value),
                    )
                    for s in _sessions.values()
                    if s.get("user_id") == current_user.id
                ]
                return SessionListResponse(sessions=user_sessions, total=len(user_sessions))
            else:
                # 未认证用户返回空列表
                return SessionListResponse(sessions=[], total=0)

    @router.get("/sessions/{session_id}", response_model=SessionState)
    async def get_session(
        session_id: str,
        current_user: Optional[AuthUser] = Depends(get_current_user)
    ):
        """
        Get session state.

        Requires authentication and session access permission.
        """
        session = _get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # 检查访问权限
        if current_user and session.get("user_id") == current_user.id:
            return SessionState(**session)

        raise HTTPException(status_code=403, detail="Access denied to this session")

    @router.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        current_user: AuthUser = Depends(get_required_user)
    ):
        """
        Delete a session.

        Requires authentication and ownership of the session.
        """
        async with _session_lock:
            if session_id not in _sessions:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

            session = _sessions[session_id]
            if session.get("user_id") != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized to delete this session")

            del _sessions[session_id]
        return {"status": "success", "message": "Session deleted"}

    # ========================================================================
    # Chat Endpoints
    # ========================================================================

    @router.post("/chat", response_model=ChatResponse)
    async def chat(
        req: ChatRequest,
        current_user: AuthUser = Depends(get_required_user)
    ):
        """
        Send a message to the agent (non-streaming).

        Supports all 5 agent styles:
        - minimal: BaseAgent (simple LLM + tools)
        - reactive: StreamingAgent (event-driven)
        - reasoning: ReactAgent (thought loop)
        - skill_based: ThreePhaseAgent (intent routing)
        - orchestrated: WorkflowAgent (DAG workflow)

        Requires authentication.
        """
        # Map API style to internal style
        style_map = {
            AgentStyleEnum.MINIMAL: AgentStyle.MINIMAL,
            AgentStyleEnum.REACTIVE: AgentStyle.REACTIVE,
            AgentStyleEnum.REASONING: AgentStyle.REASONING,
            AgentStyleEnum.SKILL_BASED: AgentStyle.SKILL_BASED,
            AgentStyleEnum.ORCHESTRATED: AgentStyle.ORCHESTRATED,
        }
        agent_style = style_map.get(req.style, AgentStyle.MINIMAL)

        # Get or create session
        session_id = req.session_id or _create_session(agent_style, current_user.id)
        session = _get_session(session_id)
        if not session:
            session_id = _create_session(agent_style, current_user.id)
            session = _sessions[session_id]

        # Create context with authenticated user
        context = Context(
            session_id=session_id,
            user_id=current_user.id,  # 使用认证用户的 ID
            variables=req.context or {},
        )

        # Create agent
        agent = create_agent_instance(
            style=agent_style,
            llm_provider="openai",
            model_name="gpt-4o-mini",
        )

        # Execute
        try:
            response = await agent.run(req.message, context)

            # Update session
            _update_session(session_id, req.message, response.text or "")

            # Convert events
            events = None
            if response.events:
                events = [
                    {"type": e.type.value, "data": e.data}
                    for e in response.events
                ]

            # Map status
            status_map = {
                AgentStatus.COMPLETED: ExecutionStatusEnum.COMPLETED,
                AgentStatus.ERROR: ExecutionStatusEnum.ERROR,
                AgentStatus.THINKING: ExecutionStatusEnum.RUNNING,
                AgentStatus.TOOLING: ExecutionStatusEnum.RUNNING,
                AgentStatus.STREAMING: ExecutionStatusEnum.RUNNING,
            }
            status = status_map.get(response.status, ExecutionStatusEnum.COMPLETED)

            return ChatResponse(
                text=response.text or "",
                status=status,
                session_id=session_id,
                style=req.style,
                events=events,
            )

        except Exception as e:
            logger.error(f"Chat execution error: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/stream")
    async def chat_stream(
        req: ChatRequest,
        request: Request,
        current_user: AuthUser = Depends(get_required_user)
    ):
        """
        Send a message to the agent (streaming).

        Returns Server-Sent Events (SSE) with real-time updates.

        Requires authentication.
        """
        # Map API style to internal style
        style_map = {
            AgentStyleEnum.MINIMAL: AgentStyle.MINIMAL,
            AgentStyleEnum.REACTIVE: AgentStyle.REACTIVE,
            AgentStyleEnum.REASONING: AgentStyle.REASONING,
            AgentStyleEnum.SKILL_BASED: AgentStyle.SKILL_BASED,
            AgentStyleEnum.ORCHESTRATED: AgentStyle.ORCHESTRATED,
        }
        agent_style = style_map.get(req.style, AgentStyle.MINIMAL)

        # Get or create session
        session_id = req.session_id or _create_session(agent_style, current_user.id)
        session = _get_session(session_id)
        if not session:
            session_id = _create_session(agent_style, current_user.id)
            session = _sessions[session_id]

        # Create context with authenticated user
        context = Context(
            session_id=session_id,
            user_id=current_user.id,  # 使用认证用户的 ID
            variables=req.context or {},
        )

        # Create agent
        agent = create_agent_instance(
            style=agent_style,
            llm_provider="openai",
            model_name="gpt-4o-mini",
        )

        async def sse_generator():
            """SSE generator that handles client disconnect."""
            try:
                full_text = ""
                async for event_str in _event_generator(agent, req.message, context):
                    # Check if client disconnected
                    if await request.is_disconnected():
                        logger.info(f"Client disconnected for session {session_id}")
                        break

                    yield event_str

                    # Accumulate text for session update
                    try:
                        event = json.loads(event_str)
                        if event.get("type") == "text":
                            full_text += event["data"].get("text", "")
                        elif event.get("type") == "done":
                            # Update session on completion
                            _update_session(session_id, req.message, full_text)
                    except (json.JSONDecodeError, KeyError):
                        pass

            except Exception as e:
                logger.error(f"SSE generator error: {e}", exc_info=e)
                yield json.dumps({
                    "type": "error",
                    "data": {"error": str(e)},
                    "timestamp": time.time(),
                }, ensure_ascii=False) + "\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ========================================================================
    # Style Information
    # ========================================================================

    @router.get("/styles")
    async def list_agent_styles():
        """List available agent styles with descriptions."""
        return {
            "styles": [
                {
                    "id": AgentStyleEnum.MINIMAL,
                    "name": "BaseAgent",
                    "description": "Simple LLM + tools. Minimal overhead, single-turn execution.",
                    "features": ["Direct LLM call", "Tool execution", "No state management"],
                    "use_case": "Simple Q&A, single-turn tasks",
                },
                {
                    "id": AgentStyleEnum.REACTIVE,
                    "name": "StreamingAgent",
                    "description": "Event-driven streaming with real-time updates (Goose-rs style).",
                    "features": ["Token streaming", "Event emission", "Inspector chain", "State machine"],
                    "use_case": "Interactive applications, real-time responses",
                },
                {
                    "id": AgentStyleEnum.REASONING,
                    "name": "ReactAgent",
                    "description": "Thought → Action → Observation loop (Claude Code style).",
                    "features": ["Explicit reasoning", "Tool planning", "Multi-step execution", "Thought history"],
                    "use_case": "Complex reasoning, multi-step problems",
                },
                {
                    "id": AgentStyleEnum.SKILL_BASED,
                    "name": "ThreePhaseAgent",
                    "description": "Intent → LLM → Tools pattern (Skill Micro Agent style).",
                    "features": ["Intent recognition", "Skill routing", "Human-in-the-loop", "Hot reload"],
                    "use_case": "Skill-based applications, intent-driven workflows",
                },
                {
                    "id": AgentStyleEnum.ORCHESTRATED,
                    "name": "WorkflowAgent",
                    "description": "DAG workflow orchestration (Goose-py style).",
                    "features": ["DAG execution", "Component nodes", "Conditional branching", "Sub-workflows"],
                    "use_case": "Complex workflows, multi-stage pipelines",
                },
            ]
        }

    # ========================================================================
    # Tool/Approval Endpoints (for future use)
    # ========================================================================

    @router.post("/sessions/{session_id}/approve")
    async def handle_approval(session_id: str, req: ApprovalRequest):
        """
        Handle approval for a pending tool call.

        (Reserved for future implementation with human-in-the-loop)
        """
        # This will be implemented when approval workflow is added
        return {"status": "not_implemented", "message": "Approval workflow not yet implemented"}

    return router


__all__ = ["create_agent_router"]
