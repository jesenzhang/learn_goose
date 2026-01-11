"""
API Request/Response Models for Pho.

This module defines Pydantic models for API requests and responses.
"""

from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class AgentStyleEnum(str, Enum):
    """Agent style options for API."""
    MINIMAL = "minimal"
    REACTIVE = "reactive"
    REASONING = "reasoning"
    SKILL_BASED = "skill_based"
    ORCHESTRATED = "orchestrated"


class ExecutionStatusEnum(str, Enum):
    """Execution status options."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


# ============================================================================
# Agent Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User message to send to agent")
    session_id: Optional[str] = Field(None, description="Session identifier (auto-generated if not provided)")
    style: Optional[AgentStyleEnum] = Field(AgentStyleEnum.MINIMAL, description="Agent style to use")
    stream: Optional[bool] = Field(False, description="Whether to stream the response")
    max_iterations: Optional[int] = Field(10, description="Max iterations for reasoning agents")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context variables")


class ChatResponse(BaseModel):
    """Response model for non-streaming chat."""
    text: str = Field(..., description="Agent response text")
    status: ExecutionStatusEnum = Field(..., description="Execution status")
    session_id: str = Field(..., description="Session identifier")
    style: AgentStyleEnum = Field(..., description="Agent style used")
    events: Optional[List[Dict[str, Any]]] = Field(None, description="Execution events")


class ToolCall(BaseModel):
    """Tool call information."""
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")
    result: Optional[Any] = Field(None, description="Tool result")
    error: Optional[str] = Field(None, description="Error message if failed")


class ThoughtStep(BaseModel):
    """Thought step in reasoning."""
    step: int = Field(..., description="Step number")
    thought: str = Field(..., description="Thought content")
    tool: Optional[str] = Field(None, description="Tool name if using tool")
    final: bool = Field(False, description="Whether this is final answer")


class StreamingEvent(BaseModel):
    """Server-Sent Event for streaming responses."""
    type: str = Field(..., description="Event type (start, thinking, text, token, tool_start, tool_end, complete, error)")
    data: Dict[str, Any] = Field(..., description="Event data")
    timestamp: float = Field(..., description="Event timestamp")


# ============================================================================
# Session Management Models
# ============================================================================

class SessionInfo(BaseModel):
    """Session information."""
    session_id: str = Field(..., description="Session identifier")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    message_count: int = Field(..., description="Number of messages")
    style: AgentStyleEnum = Field(..., description="Agent style used")


class SessionListResponse(BaseModel):
    """Response for session list."""
    sessions: List[SessionInfo] = Field(..., description="List of sessions")
    total: int = Field(..., description="Total number of sessions")


class SessionState(BaseModel):
    """Complete session state."""
    session_id: str = Field(..., description="Session identifier")
    messages: List[Dict[str, Any]] = Field(..., description="Conversation history")
    variables: Dict[str, Any] = Field(..., description="Session variables")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


# ============================================================================
# Workflow Request/Response Models
# ============================================================================

class WorkflowSaveRequest(BaseModel):
    """Request to save a workflow."""
    workflow: Dict[str, Any] = Field(..., description="Workflow definition (VueFlow format)")
    title: str = Field(..., description="Workflow title")


class WorkflowResponse(BaseModel):
    """Workflow data response."""
    id: str = Field(..., description="Workflow ID")
    title: str = Field(..., description="Workflow title")
    workflow: Dict[str, Any] = Field(..., description="Workflow definition")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class WorkflowListResponse(BaseModel):
    """Response for workflow list."""
    workflows: List[WorkflowResponse] = Field(..., description="List of workflows")
    total: int = Field(..., description="Total number of workflows")


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow."""
    workflow_id: str = Field(..., description="Workflow ID to execute")
    inputs: Optional[Dict[str, Any]] = Field(None, description="Input data for workflow")


class WorkflowExecuteResponse(BaseModel):
    """Response from workflow execution."""
    execution_id: str = Field(..., description="Execution ID")
    status: ExecutionStatusEnum = Field(..., description="Execution status")
    outputs: Optional[Dict[str, Any]] = Field(None, description="Output data")
    error: Optional[str] = Field(None, description="Error message if failed")


# ============================================================================
# Health & System Models
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    service: str = Field(default="pho", description="Service name")


class ErrorResponse(BaseModel):
    """Error response."""
    code: int = Field(..., description="HTTP status code")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error info")


# ============================================================================
# Approval Models (for human-in-the-loop)
# ============================================================================

class ApprovalRequest(BaseModel):
    """Request for approval handling."""
    approved: bool = Field(..., description="Whether the action is approved")
    feedback: Optional[str] = Field("", description="Optional feedback for rejection")


class ToolApprovalInfo(BaseModel):
    """Tool call awaiting approval."""
    tool_name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")
    session_id: str = Field(..., description="Session identifier")
    step_number: int = Field(..., description="Step number")
