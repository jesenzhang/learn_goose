"""
Workflow Routes - RESTful endpoints for workflow management.

This module provides endpoints for:
- Workflow CRUD operations
- Workflow execution
- Workflow import/export (VueFlow format)
"""

import json
import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from pho.api.schemas import (
    WorkflowSaveRequest,
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowExecuteRequest,
    WorkflowExecuteResponse,
    ExecutionStatusEnum,
    HealthResponse,
)

logger = logging.getLogger(__name__)


# ============================================================================
# In-Memory Workflow Storage (simplified, replace with DB in production)
# ============================================================================

_workflows: Dict[str, Dict[str, Any]] = {}
_executions: Dict[str, Dict[str, Any]] = {}


def _save_workflow(workflow_id: str, title: str, workflow: Dict[str, Any]) -> str:
    """Save a workflow."""
    now = datetime.utcnow().isoformat()
    if workflow_id:
        # Update existing
        if workflow_id in _workflows:
            _workflows[workflow_id]["title"] = title
            _workflows[workflow_id]["workflow"] = workflow
            _workflows[workflow_id]["updated_at"] = now
        else:
            _workflows[workflow_id] = {
                "id": workflow_id,
                "title": title,
                "workflow": workflow,
                "created_at": now,
                "updated_at": now,
            }
        return workflow_id
    else:
        # Create new
        new_id = str(uuid.uuid4())
        _workflows[new_id] = {
            "id": new_id,
            "title": title,
            "workflow": workflow,
            "created_at": now,
            "updated_at": now,
        }
        return new_id


# ============================================================================
# Router Creation
# ============================================================================

def create_workflow_router() -> APIRouter:
    """Create and configure the workflow API router."""
    router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])

    # ========================================================================
    # Health Check
    # ========================================================================

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "workflow-api"}

    # ========================================================================
    # Workflow CRUD
    # ========================================================================

    @router.post("/", response_model=WorkflowResponse)
    async def save_workflow(req: WorkflowSaveRequest):
        """
        Save or update a workflow.

        Args:
            req: Workflow save request with definition and title

        Returns:
            Saved workflow with ID
        """
        try:
            workflow_id = _save_workflow(None, req.title, req.workflow)
            workflow = _workflows[workflow_id]
            return WorkflowResponse(**workflow)
        except Exception as e:
            logger.error(f"Failed to save workflow: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/{workflow_id}", response_model=WorkflowResponse)
    async def update_workflow(workflow_id: str, req: WorkflowSaveRequest):
        """
        Update an existing workflow.

        Args:
            workflow_id: Workflow ID to update
            req: Updated workflow data

        Returns:
            Updated workflow
        """
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        try:
            updated_id = _save_workflow(workflow_id, req.title, req.workflow)
            workflow = _workflows[updated_id]
            return WorkflowResponse(**workflow)
        except Exception as e:
            logger.error(f"Failed to update workflow {workflow_id}: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{workflow_id}", response_model=WorkflowResponse)
    async def get_workflow(workflow_id: str):
        """
        Get a workflow by ID.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow data
        """
        workflow = _workflows.get(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        return WorkflowResponse(**workflow)

    @router.get("/", response_model=WorkflowListResponse)
    async def list_workflows(page: int = 1, size: int = 20):
        """
        List all workflows.

        Args:
            page: Page number (1-indexed)
            size: Page size

        Returns:
            Paginated list of workflows
        """
        workflows = list(_workflows.values())
        start = (page - 1) * size
        end = start + size
        paginated = workflows[start:end]

        return WorkflowListResponse(
            workflows=[WorkflowResponse(**w) for w in paginated],
            total=len(workflows),
        )

    @router.delete("/{workflow_id}")
    async def delete_workflow(workflow_id: str):
        """
        Delete a workflow.

        Args:
            workflow_id: Workflow ID to delete

        Returns:
            Success confirmation
        """
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        del _workflows[workflow_id]
        return {"status": "success", "message": f"Workflow {workflow_id} deleted"}

    # ========================================================================
    # Workflow Execution
    # ========================================================================

    @router.post("/{workflow_id}/execute", response_model=WorkflowExecuteResponse)
    async def execute_workflow(workflow_id: str, inputs: Optional[Dict[str, Any]] = None):
        """
        Execute a workflow.

        Args:
            workflow_id: Workflow ID to execute
            inputs: Optional input data for the workflow

        Returns:
            Execution result with status and outputs
        """
        workflow = _workflows.get(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Create execution record
        execution_id = str(uuid.uuid4())
        _executions[execution_id] = {
            "id": execution_id,
            "workflow_id": workflow_id,
            "status": ExecutionStatusEnum.RUNNING,
            "inputs": inputs or {},
            "outputs": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            # TODO: Implement actual workflow execution
            # For now, return a mock response
            logger.info(f"Executing workflow {workflow_id} (execution {execution_id})")

            # Mock execution
            _executions[execution_id]["status"] = ExecutionStatusEnum.COMPLETED
            _executions[execution_id]["outputs"] = {
                "result": f"Mock execution of workflow {workflow_id}",
                "inputs_received": inputs or {},
            }

            return WorkflowExecuteResponse(
                execution_id=execution_id,
                status=ExecutionStatusEnum.COMPLETED,
                outputs=_executions[execution_id]["outputs"],
            )

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=e)
            _executions[execution_id]["status"] = ExecutionStatusEnum.ERROR
            _executions[execution_id]["error"] = str(e)

            return WorkflowExecuteResponse(
                execution_id=execution_id,
                status=ExecutionStatusEnum.ERROR,
                error=str(e),
            )

    @router.get("/executions/{execution_id}", response_model=WorkflowExecuteResponse)
    async def get_execution(execution_id: str):
        """
        Get execution status and results.

        Args:
            execution_id: Execution ID

        Returns:
            Execution data
        """
        execution = _executions.get(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

        return WorkflowExecuteResponse(**execution)

    @router.get("/{workflow_id}/executions")
    async def list_workflow_executions(workflow_id: str):
        """
        List all executions for a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            List of executions
        """
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        executions = [
            e for e in _executions.values() if e.get("workflow_id") == workflow_id
        ]
        return {"executions": executions, "total": len(executions)}

    # ========================================================================
    # Workflow Import/Export
    # ========================================================================

    @router.post("/import")
    async def import_workflow(data: Dict[str, Any], format: str = "vueflow"):
        """
        Import a workflow from external format.

        Supported formats:
        - vueflow: VueFlow JSON format
        - json: Generic JSON workflow

        Args:
            data: Workflow data
            format: Import format

        Returns:
            Imported workflow with ID
        """
        try:
            if format == "vueflow":
                # Extract title from data or use default
                title = data.get("title", "Imported Workflow")
                workflow_id = _save_workflow(None, title, data)
                return {"id": workflow_id, "message": "Workflow imported successfully"}
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

        except Exception as e:
            logger.error(f"Failed to import workflow: {e}", exc_info=e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{workflow_id}/export")
    async def export_workflow(workflow_id: str, format: str = "vueflow"):
        """
        Export a workflow in specified format.

        Args:
            workflow_id: Workflow ID to export
            format: Export format (vueflow, json)

        Returns:
            Workflow data in requested format
        """
        workflow = _workflows.get(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        if format == "vueflow":
            return workflow["workflow"]
        elif format == "json":
            return {
                "id": workflow["id"],
                "title": workflow["title"],
                "workflow": workflow["workflow"],
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    # ========================================================================
    # Workflow Validation
    # ========================================================================

    @router.post("/validate")
    async def validate_workflow(data: Dict[str, Any]):
        """
        Validate a workflow definition.

        Args:
            data: Workflow definition to validate

        Returns:
            Validation result with errors/warnings
        """
        errors = []
        warnings = []

        # Basic validation
        if "nodes" not in data:
            errors.append("Missing 'nodes' field")
        elif not isinstance(data["nodes"], list):
            errors.append("'nodes' must be a list")

        if "edges" not in data:
            errors.append("Missing 'edges' field")
        elif not isinstance(data["edges"], list):
            errors.append("'edges' must be a list")

        # Check for entry node
        if "nodes" in data:
            has_entry = any(n.get("data", {}).get("type") == "entry" for n in data["nodes"])
            if not has_entry:
                warnings.append("No entry node found - workflow may not start properly")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    return router


__all__ = ["create_workflow_router"]
