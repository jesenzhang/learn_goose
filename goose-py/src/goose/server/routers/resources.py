# opencoze/server/routers/resources.py

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body

from opencoze.server.dependencies import get_resource_service
from opencoze.app.services.resource import ResourceService
from opencoze.server.dto import ApiResponse
from opencoze.core.protocol import (
    ModelDefinition, KnowledgeDefinition, 
    ResourceMetadata, DomainType, ResourceType
)
from opencoze.infra.logging import get_logger

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])
logger = get_logger("server.routers.resources")

# --- Read ---

@router.get("/list", response_model=ApiResponse[List[Any]])
async def list_resources(
    type: str = Query(ResourceType.MODEL), # 使用 ResourceType 枚举值
    service: ResourceService = Depends(get_resource_service)
):
    try:
        # Service 内部会处理 Domain 映射和对象转换
        data = await service.list(type)
        
        # 转为 Metadata (DTO)
        results = []
        for item in data:
            if hasattr(item, "to_metadata"):
                results.append(item.to_metadata())
            else:
                results.append(item)
        return ApiResponse(data=results)
    except Exception as e:
        logger.error(f"List failed: {e}")
        raise HTTPException(500, str(e))

@router.get("/models", response_model=ApiResponse[List[ResourceMetadata]])
async def list_models(
    model_type: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    service: ResourceService = Depends(get_resource_service)
):
    filters = {}
    if model_type: filters["model_type"] = model_type
    if provider: filters["provider"] = provider
    
    data = await service.list(ResourceType.MODEL, filters=filters)
    return ApiResponse(data=[m.to_metadata() for m in data])

@router.get("/tools", response_model=ApiResponse[List[Any]])
async def list_tools(service: ResourceService = Depends(get_resource_service)):
    data = await service.list(ResourceType.TOOL)
    return ApiResponse(data=[t.to_metadata() for t in data])

# --- Write ---

@router.post("/model/create")
async def create_model(
    model: ModelDefinition,
    service: ResourceService = Depends(get_resource_service)
):
    try:
        mid = await service.save_resource(ResourceType.MODEL, model)
        return ApiResponse(data={"id": mid})
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/knowledge/create")
async def create_knowledge(
    name: str = Body(..., embed=True),
    embedding_model: str = Body(..., embed=True),
    description: str = Body("", embed=True),
    service: ResourceService = Depends(get_resource_service)
):
    try:
        kb = KnowledgeDefinition(
            id="", # Service will generate
            name=name,
            description=description,
            embedding_model_id=embedding_model,
            vector_store_config={"type": "chroma"},
            doc_count=0
        )
        kid = await service.create_knowledge_base(kb) # 调用特定业务方法
        return ApiResponse(data={"id": kid})
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/plugins/import")
async def import_plugin(
    payload: Dict[str, Any] = Body(...),
    service: ResourceService = Depends(get_resource_service)
):
    try:
        pid = await service.import_plugin(
            name=payload.get("name", "Plugin"),
            schema=payload.get("schema"),
            icon=payload.get("icon", "plug")
        )
        return ApiResponse(data={"id": pid})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/{resource_id:path}")
async def delete_resource(
    resource_id: str,
    type: str = Query(..., description="Resource Type"),
    service: ResourceService = Depends(get_resource_service)
):
    success = await service.delete(type, resource_id)
    if not success:
        raise HTTPException(404, "Not found")
    return ApiResponse(data={"success": True})