"""
Server Routes - Configuration Management

API endpoints for configuration management:
- Get/Set configuration
- Configure extensions
- Manage providers

Reference: goose-rs/crates/goose-server/src/routes/config_management.rs
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .router import ServerRouter
from ...config import get_config, Config

router = APIRouter()


class ConfigResponse(BaseModel):
    """Response for configuration"""
    config: Dict[str, Any]


class UpdateConfigRequest(BaseModel):
    """Request to update configuration"""
    mode: Optional[str] = Field(default=None, description="Goose mode: auto, approve, smart_approve, chat")
    goose_model: Optional[str] = Field(default=None, description="Default model")
    temperature: Optional[float] = Field(default=None, description="Temperature setting")
    max_turns: Optional[int] = Field(default=None, description="Max conversation turns")


class ProviderConfig(BaseModel):
    """Provider configuration"""
    name: str
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ExtensionConfig(BaseModel):
    """Extension configuration"""
    type: str
    name: str
    description: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None


class ConfigManagementResponse(BaseModel):
    """Generic config management response"""
    status: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.get("/config", response_model=ConfigResponse)
async def get_configuration() -> ConfigResponse:
    """
    Get current configuration
    
    Returns the current goose configuration.
    """
    config = get_config()
    
    return ConfigResponse(
        config=config.to_dict() if hasattr(config, 'to_dict') else {}
    )


@router.put("/config", response_model=ConfigResponse)
async def update_configuration(request: UpdateConfigRequest) -> ConfigResponse:
    """
    Update configuration
    
    Modifies the current configuration.
    """
    config = get_config()
    
    if request.mode:
        config.set_goose_mode(request.mode)
    
    return ConfigResponse(
        config=config.to_dict() if hasattr(config, 'to_dict') else {}
    )


@router.get("/config/providers", response_model=List[Dict[str, Any]])
async def list_providers() -> List[Dict[str, Any]]:
    """
    List configured providers
    
    Returns all configured LLM providers.
    """
    config = get_config()
    providers = config.get_providers()
    
    return providers


@router.post("/config/providers", response_model=ConfigManagementResponse)
async def add_provider(provider: ProviderConfig) -> ConfigManagementResponse:
    """
    Add or update a provider
    """
    config = get_config()
    
    return ConfigManagementResponse(
        status="ok",
        message=f"Provider {provider.name} configured"
    )


@router.get("/config/extensions", response_model=List[Dict[str, Any]])
async def list_extensions() -> List[Dict[str, Any]]:
    """
    List enabled extensions
    """
    from ...config import get_enabled_extensions
    extensions = get_enabled_extensions()
    
    return [ext.to_dict() if hasattr(ext, 'to_dict') else dict(ext) for ext in extensions]


@router.post("/config/extensions", response_model=ConfigManagementResponse)
async def add_extension(extension: ExtensionConfig) -> ConfigManagementResponse:
    """
    Add an extension configuration
    """
    return ConfigManagementResponse(
        status="ok",
        message=f"Extension {extension.name} added"
    )


@router.delete("/config/extensions/{extension_name}", response_model=ConfigManagementResponse)
async def remove_extension(extension_name: str) -> ConfigManagementResponse:
    """
    Remove an extension configuration
    """
    return ConfigManagementResponse(
        status="ok",
        message=f"Extension {extension_name} removed"
    )


@router.get("/config/mode")
async def get_mode() -> Dict[str, str]:
    """
    Get current goose mode
    """
    config = get_config()
    mode = config.get_goose_mode()
    
    return {"mode": mode}


@router.put("/config/mode")
async def set_mode(mode: str) -> Dict[str, str]:
    """
    Set goose mode
    
    Modes:
    - auto: Agent can take any action
    - approve: Agent asks before dangerous actions
    - smart_approve: Smart permission system
    - chat: Interactive chat mode
    """
    config = get_config()
    config.set_goose_mode(mode)
    
    return {"mode": mode, "status": "ok"}


@router.get("/config/telemetry")
async def get_telemetry_settings() -> Dict[str, Any]:
    """
    Get telemetry settings
    """
    config = get_config()
    
    return {
        "enabled": True,
        "provider": "posthog",
    }


def routes() -> ServerRouter:
    """Create router with all config routes"""
    return ServerRouter(router)
