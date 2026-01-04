# opencoze/server/routers/components.py
import asyncio
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request

from opencoze.server.dto import ApiResponse, CreateApiComponentReq, ComponentView
from opencoze.server.dependencies import get_resource_service
from opencoze.app.services.resource import ResourceService
from opencoze.infra.adapters import AdapterManager
from opencoze.infra.logging import get_logger

router = APIRouter(prefix="/api/v1/components", tags=["components"])
logger = get_logger("server.routers.components")

@router.get("/", response_model=ApiResponse[Dict[str, List[ComponentView]]])
async def list_components_library(
    format: str = "vueflow", # 支持格式参数
    service: ResourceService = Depends(get_resource_service)
):
    """
    获取组件库 (分组)
    """
    try:
        # 1. 从 Service 获取全量组件 (Core Logic)
        library = await service.get_component_library()
        result = AdapterManager.export_components(library,format_type=format) 
        
        return ApiResponse(data=result)
        
    except Exception as e:
        logger.error(f"Failed to list components: {e}", exc_info=True)
        raise HTTPException(500, "Internal Server Error")

@router.post("/generate_api", response_model=ApiResponse[Dict])
async def generate_api_component(
    req: CreateApiComponentReq,
    service: ResourceService = Depends(get_resource_service)
):
    """
    动态生成 API 组件
    1. 注册到当前内存 (Hot Load)
    2. 持久化到数据库 (Persist)
    """
    try:
        # 核心逻辑全部委托给 Service
        key = await service.create_api_component(req)
        return ApiResponse(data={"key": key, "msg": "Component created successfully"})
        
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Generate component failed: {e}", exc_info=True)
        raise HTTPException(500, str(e))