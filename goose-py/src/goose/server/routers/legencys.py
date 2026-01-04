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

router = APIRouter(prefix="/api/v1", tags=["resources"])
logger = get_logger("server.routers.legencys")

@router.get("/models", response_model=ApiResponse[List[ResourceMetadata]])
async def list_models(
    model_type: Optional[str] = Query(None, alias="model_type", description="筛选模型类型 (llm, embedding,rerank)"),
    provider: Optional[str] = Query(None, description="筛选供应商 (openai, local)"),
    res_mgr: ResourceService = Depends(get_resource_service)
):
    """获取模型列表 (支持过滤 embedding/rerank/llm)"""
    try:
       # 1. 构造过滤器
        filters = {}
        if model_type:
            filters["model_type"] = model_type
        if provider:
            filters["provider"] = provider

        # 2. 调用带过滤的 List
        # 注意：现在 list() 直接返回 List[ResourceMetadata]，不需要再在 Router 里转换了
        data = res_mgr.list(DomainType.MODELS, filters=filters)
        return ApiResponse(data=data)
    except Exception as e:
        logger.error(f"List models failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tools", response_model=ApiResponse[List[Any]])
async def list_tools(reader: ResourceService = Depends(get_resource_service)):
    """
    获取工具列表
    包含: System Tools (内置), Plugin Tools (OpenAPI), Workflow Tools (发布的工作流)
    """
    try:
        data = reader.list(DomainType.TOOLS)
        # 转换为 Metadata
        results = [t.to_metadata() for t in data if hasattr(t, "to_metadata")]
        return ApiResponse(data=results)
    except Exception as e:
        logger.error(f"List tools failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
