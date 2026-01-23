"""
Server Routes - Session Management

API endpoints for session management:
- List sessions
- Get/Delete session
- Export/Import sessions
- Update session name
- Edit messages

Reference: goose-rs/crates/goose-server/src/routes/session.rs
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from .router import ServerRouter
from ...session import SessionManager

router = APIRouter()


class SessionListResponse(BaseModel):
    """Response for listing sessions"""
    sessions: List[Dict[str, Any]]


class GetSessionResponse(BaseModel):
    """Response for getting a session"""
    session: Dict[str, Any]


class UpdateSessionNameRequest(BaseModel):
    """Request to update session name"""
    name: str = Field(..., max_length=200, description="New session name")


class UpdateSessionUserRecipeValuesRequest(BaseModel):
    """Request to update user recipe values"""
    user_recipe_values: Dict[str, str] = Field(default_factory=dict)


class ImportSessionRequest(BaseModel):
    """Request to import a session"""
    json: str = Field(..., description="JSON representation of session")


class EditMessageRequest(BaseModel):
    """Request to edit a message"""
    timestamp: int = Field(..., description="Message timestamp to edit from")
    edit_type: str = Field(default="fork", description="Edit type: fork or edit")


class EditMessageResponse(BaseModel):
    """Response for message editing"""
    session_id: str


class SessionExtensionsResponse(BaseModel):
    """Response for session extensions"""
    extensions: List[Dict[str, Any]]


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    """
    List all sessions
    
    Returns a list of all available sessions.
    """
    session_manager = SessionManager.get_instance()
    sessions = await session_manager.list_sessions()
    
    return SessionListResponse(
        sessions=[s.to_dict() if hasattr(s, 'to_dict') else dict(s) for s in sessions]
    )


@router.get("/sessions/{session_id}", response_model=GetSessionResponse)
async def get_session(session_id: str) -> GetSessionResponse:
    """
    Get a session by ID
    
    Returns the full session details including conversation history.
    """
    session_manager = SessionManager.get_instance()
    session = await session_manager.get_session(session_id, include_messages=True)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    return GetSessionResponse(
        session=session.to_dict() if hasattr(session, 'to_dict') else dict(session)
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def delete_session(session_id: str) -> Dict[str, str]:
    """
    Delete a session
    
    Removes the session and its associated data.
    """
    session_manager = SessionManager.get_instance()
    
    success = await session_manager.delete_session(session_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    return {"status": "ok", "session_id": session_id}


@router.put("/sessions/{session_id}/name", status_code=status.HTTP_200_OK)
async def update_session_name(
    session_id: str,
    request: UpdateSessionNameRequest
) -> Dict[str, str]:
    """
    Update session name
    """
    session_manager = SessionManager.get_instance()
    
    await session_manager.update(session_id).apply()
    
    return {"status": "ok", "session_id": session_id}


@router.put("/sessions/{session_id}/user_recipe_values")
async def update_session_user_recipe_values(
    session_id: str,
    request: UpdateSessionUserRecipeValuesRequest
) -> Dict[str, Any]:
    """
    Update user recipe values for a session
    """
    session_manager = SessionManager.get_instance()
    
    session = await session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    return {"status": "ok", "session_id": session_id}


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str) -> Dict[str, str]:
    """
    Export a session as JSON
    """
    session_manager = SessionManager.get_instance()
    exported = await session_manager.export_session(session_id)
    
    return {"json": exported}


@router.post("/sessions/import", response_model=Dict[str, Any])
async def import_session(request: ImportSessionRequest) -> Dict[str, Any]:
    """
    Import a session from JSON
    """
    session_manager = SessionManager.get_instance()
    session = await session_manager.import_session(request.json)
    
    return session.to_dict() if hasattr(session, 'to_dict') else dict(session)


@router.post("/sessions/{session_id}/edit_message", response_model=EditMessageResponse)
async def edit_message(
    session_id: str,
    request: EditMessageRequest
) -> EditMessageResponse:
    """
    Edit a message in the session
    
    Creates a fork or truncates the conversation.
    """
    session_manager = SessionManager.get_instance()
    
    if request.edit_type == "fork":
        new_session = await session_manager.copy_session(session_id, "(edited)")
        await session_manager.truncate_conversation(new_session.id, request.timestamp)
        return EditMessageResponse(session_id=new_session.id)
    else:
        await session_manager.truncate_conversation(session_id, request.timestamp)
        return EditMessageResponse(session_id=session_id)


@router.get("/sessions/{session_id}/extensions", response_model=SessionExtensionsResponse)
async def get_session_extensions(session_id: str) -> SessionExtensionsResponse:
    """
    Get extensions for a session
    """
    session_manager = SessionManager.get_instance()
    session = await session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    extensions = []
    if hasattr(session, 'extension_data') and session.extension_data:
        extensions = list(session.extension_data.values())
    
    return SessionExtensionsResponse(extensions=extensions)


def routes() -> ServerRouter:
    """Create router with all session routes"""
    return ServerRouter(router)
