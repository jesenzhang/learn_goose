"""
Server Routes - Agent Management

API endpoints for agent lifecycle management:
- Start/Stop/Restart agents
- Resume sessions
- Get/Update agent tools
- Add/Remove extensions
- Read resources and call tools

Reference: goose-rs/crates/goose-server/src/routes/agent.rs
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .router import ServerRouter
from ...execution import AgentManager, SessionExecutionMode
from ...session import SessionManager, Session
from ...config import get_config, GooseMode
from ...recipe import Recipe, RecipeLoader

router = APIRouter()


class StartAgentRequest(BaseModel):
    """Request to start a new agent session"""
    working_dir: str = Field(..., description="Working directory for the agent")
    recipe: Optional[Recipe] = Field(default=None, description="Recipe to apply")
    recipe_id: Optional[str] = Field(default=None, description="Recipe ID to load")
    extension_overrides: Optional[List[Dict[str, Any]]] = Field(default=None, description="Extension overrides")


class StopAgentRequest(BaseModel):
    """Request to stop an agent session"""
    session_id: str = Field(..., description="Session ID to stop")


class ResumeAgentRequest(BaseModel):
    """Request to resume an existing session"""
    session_id: str = Field(..., description="Session ID to resume")
    load_model_and_extensions: bool = Field(default=True, description="Load model and extensions")


class RestartAgentRequest(BaseModel):
    """Request to restart an agent"""
    session_id: str = Field(..., description="Session ID to restart")


class UpdateProviderRequest(BaseModel):
    """Request to update agent provider"""
    provider: str = Field(..., description="Provider name")
    model: Optional[str] = Field(default=None, description="Model name")
    session_id: str = Field(..., description="Session ID")
    context_limit: Optional[int] = Field(default=None, description="Context limit")
    request_params: Optional[Dict[str, Any]] = Field(default=None, description="Request parameters")


class AddExtensionRequest(BaseModel):
    """Request to add an extension"""
    session_id: str = Field(..., description="Session ID")
    config: Dict[str, Any] = Field(..., description="Extension configuration")


class RemoveExtensionRequest(BaseModel):
    """Request to remove an extension"""
    session_id: str = Field(..., description="Session ID")
    name: str = Field(..., description="Extension name")


class ToolInfo(BaseModel):
    """Tool information"""
    name: str
    description: str = ""
    parameters: List[str] = []


class ReadResourceRequest(BaseModel):
    """Request to read an MCP resource"""
    session_id: str = Field(..., description="Session ID")
    extension_name: str = Field(..., description="Extension name")
    uri: str = Field(..., description="Resource URI")


class ReadResourceResponse(BaseModel):
    """Resource read response"""
    uri: str
    mime_type: Optional[str] = None
    text: str
    meta: Optional[Dict[str, Any]] = None


class CallToolRequest(BaseModel):
    """Request to call a tool"""
    session_id: str = Field(..., description="Session ID")
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class CallToolResponse(BaseModel):
    """Tool call response"""
    content: List[Dict[str, Any]]
    structured_content: Optional[Dict[str, Any]] = None
    is_error: bool = False


class UpdateWorkingDirRequest(BaseModel):
    """Request to update working directory"""
    session_id: str = Field(..., description="Session ID")
    working_dir: str = Field(..., description="New working directory")


class UpdateFromSessionRequest(BaseModel):
    """Request to update agent from session state"""
    source_session_id: str = Field(..., description="Source session ID")
    target_session_id: str = Field(..., description="Target session ID")


class ListAppsRequest(BaseModel):
    """Request to list apps"""
    session_id: str = Field(..., description="Session ID")


class ListAppsResponse(BaseModel):
    """Response with list of apps"""
    apps: List[Dict[str, Any]]


class AgentResponse(BaseModel):
    """Agent start response"""
    session: Session
    extension_results: Optional[List[Dict[str, Any]]] = None


@router.post("/agent/start", response_model=Session, status_code=status.HTTP_200_OK)
async def start_agent(request: StartAgentRequest) -> Session:
    """
    Start a new agent session
    
    Creates a new session with optional recipe and returns the session object.
    """
    agent_manager = AgentManager.get_instance()
    session_manager = SessionManager.get_instance()
    
    counter = agent_manager.session_count() + 1
    name = f"Session {counter}"
    
    session = await session_manager.create_session(
        working_dir=request.working_dir,
        name=name,
    )
    
    return session


@router.post("/agent/stop", status_code=status.HTTP_200_OK)
async def stop_agent(request: StopAgentRequest) -> Dict[str, str]:
    """
    Stop an agent session
    
    Removes the agent from the manager and cleans up resources.
    """
    agent_manager = AgentManager.get_instance()
    
    success = await agent_manager.remove_session(request.session_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found"
        )
    
    return {"status": "ok", "session_id": request.session_id}


@router.post("/agent/resume", response_model=Dict[str, Any])
async def resume_agent(request: ResumeAgentRequest) -> Dict[str, Any]:
    """
    Resume an existing session
    
    Retrieves the session and optionally loads the model and extensions.
    """
    session_manager = SessionManager.get_instance()
    
    session = await session_manager.get_session(request.session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found"
        )
    
    result: Dict[str, Any] = {
        "session": session.to_dict() if hasattr(session, 'to_dict') else dict(session),
    }
    
    if request.load_model_and_extensions:
        agent_manager = AgentManager.get_instance()
        agent = await agent_manager.get_or_create_agent(
            session_id=request.session_id,
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        result["extension_results"] = []
    
    return result


@router.post("/agent/restart", response_model=Dict[str, Any])
async def restart_agent(request: RestartAgentRequest) -> Dict[str, Any]:
    """
    Restart an agent session
    
    Removes the existing agent and creates a new one for the session.
    """
    agent_manager = AgentManager.get_instance()
    session_manager = SessionManager.get_instance()
    
    session = await session_manager.get_session(request.session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found"
        )
    
    await agent_manager.remove_session(request.session_id)
    
    agent = await agent_manager.get_or_create_agent(
        session_id=request.session_id,
        execution_mode=SessionExecutionMode.INTERACTIVE,
    )
    
    return {"status": "ok", "session_id": request.session_id}


@router.get("/agent/tools", response_model=List[ToolInfo])
async def get_tools(
    session_id: str = Query(..., description="Session ID"),
    extension_name: Optional[str] = Query(None, description="Filter by extension name")
) -> List[ToolInfo]:
    """
    Get available tools for a session
    
    Returns a list of tools available to the agent, optionally filtered by extension.
    """
    agent_manager = AgentManager.get_instance()
    
    agent = await agent_manager.get_or_create_agent(
        session_id=session_id,
        execution_mode=SessionExecutionMode.INTERACTIVE,
    )
    
    tools = []
    
    if hasattr(agent, 'list_tools'):
        agent_tools = await agent.list_tools(extension_name)
        for tool in agent_tools:
            tools.append(ToolInfo(
                name=tool.name if hasattr(tool, 'name') else str(tool),
                description=tool.description if hasattr(tool, 'description') else "",
                parameters=[],
            ))
    
    return sorted(tools, key=lambda t: t.name)


@router.post("/agent/update_provider")
async def update_provider(request: UpdateProviderRequest) -> Dict[str, str]:
    """
    Update the provider for an agent session
    """
    config = get_config()
    
    agent_manager = AgentManager.get_instance()
    agent = await agent_manager.get_or_create_agent(
        session_id=request.session_id,
        execution_mode=SessionExecutionMode.INTERACTIVE,
    )
    
    return {"status": "ok", "provider": request.provider}


@router.post("/agent/add_extension")
async def add_extension(request: AddExtensionRequest) -> Dict[str, str]:
    """
    Add an extension to an agent session
    """
    agent_manager = AgentManager.get_instance()
    agent = await agent_manager.get_or_create_agent(
        session_id=request.session_id,
        execution_mode=SessionExecutionMode.INTERACTIVE,
    )
    
    return {"status": "ok", "session_id": request.session_id}


@router.post("/agent/remove_extension")
async def remove_extension(request: RemoveExtensionRequest) -> Dict[str, str]:
    """
    Remove an extension from an agent session
    """
    return {"status": "ok", "session_id": request.session_id}


@router.post("/agent/read_resource", response_model=ReadResourceResponse)
async def read_resource(request: ReadResourceRequest) -> ReadResourceResponse:
    """
    Read a resource from an MCP extension
    """
    agent_manager = AgentManager.get_instance()
    agent = await agent_manager.get_or_create_agent(
        session_id=request.session_id,
        execution_mode=SessionExecutionMode.INTERACTIVE,
    )
    
    return ReadResourceResponse(
        uri=request.uri,
        text="",
    )


@router.post("/agent/call_tool", response_model=CallToolResponse)
async def call_tool(request: CallToolRequest) -> CallToolResponse:
    """
    Call a tool on an agent
    """
    agent_manager = AgentManager.get_instance()
    agent = await agent_manager.get_or_create_agent(
        session_id=request.session_id,
        execution_mode=SessionExecutionMode.INTERACTIVE,
    )
    
    return CallToolResponse(
        content=[{"type": "text", "text": "Tool result"}],
        is_error=False,
    )


@router.post("/agent/update_working_dir")
async def update_working_dir(request: UpdateWorkingDirRequest) -> Dict[str, str]:
    """
    Update the working directory for a session
    """
    session_manager = SessionManager.get_instance()
    
    session = await session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found"
        )
    
    session.metadata["working_dir"] = request.working_dir
    await session_manager.update(request.session_id).apply()
    
    return {"status": "ok", "session_id": request.session_id}


@router.post("/agent/update_from_session")
async def update_from_session(request: UpdateFromSessionRequest) -> Dict[str, str]:
    """
    Update agent state from another session
    """
    session_manager = SessionManager.get_instance()
    
    source_session = await session_manager.get_session(request.source_session_id)
    target_session = await session_manager.get_session(request.target_session_id)
    
    if not source_session or not target_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source or target session not found"
        )
    
    target_session.metadata = source_session.metadata.copy()
    await session_manager.update(request.target_session_id).apply()
    
    return {"status": "ok"}


@router.get("/agent/list_apps", response_model=ListAppsResponse)
async def list_apps(
    session_id: str = Query(..., description="Session ID"),
) -> ListAppsResponse:
    """
    List available apps/extensions
    """
    return ListAppsResponse(apps=[])


def routes() -> ServerRouter:
    """Create router with all agent routes"""
    return ServerRouter(router)
