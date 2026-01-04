from fastapi import APIRouter, Depends, HTTPException, status
from typing import List,Dict

from goose.server.schemas import ApiResponse, CreateAppReq, UpdateAppReq, AppResponse
from goose.server.dependencies import get_app_service
from goose.app.services.app import AppService


router = APIRouter(prefix="/api/v1/apps", tags=["Apps"])

@router.post("/", response_model=ApiResponse[Dict])
async def create_app(
    req: CreateAppReq,
    service: AppService = Depends(get_app_service)
):
    # TODO: 从 Token 获取 user_id
    creator_id = "user_default" 
    try:
        app_id = await service.create_app(req, creator_id)
        return ApiResponse(data={"id": app_id})
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

@router.get("/{app_id}", response_model=ApiResponse[AppResponse])
async def get_app(
    app_id: str,
    service: AppService = Depends(get_app_service)
):
    app = await service.get_app(app_id)
    if not app:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "App not found")
    return ApiResponse(data=app)

@router.patch("/{app_id}")
async def update_app(
    app_id: str,
    req: UpdateAppReq,
    service: AppService = Depends(get_app_service)
):
    success = await service.update_app(app_id, req)
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "App not found")
    return ApiResponse(data={"msg": "Updated"})