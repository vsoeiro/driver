"""Admin routes for runtime settings."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.dependencies import DBSession
from backend.schemas.admin import (
    ObservabilitySnapshot,
    PluginSettingFieldResponse,
    PluginSettingsGroupResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from backend.services.app_settings import AppSettingsService, RuntimeSettings
from backend.services.metadata_libraries.settings import MetadataLibrarySettingsService
from backend.services.observability import ObservabilityService, clear_observability_cache

router = APIRouter(prefix="/admin", tags=["Admin"])
MASKED_SECRET_VALUE = "********"


def _mask_secret(value: str | None) -> tuple[str | None, bool]:
    configured = bool(str(value or "").strip())
    return (MASKED_SECRET_VALUE if configured else None), configured


def _build_runtime_settings_response(
    settings: RuntimeSettings,
    plugin_groups: list[dict[str, Any]],
) -> RuntimeSettingsResponse:
    masked_key, key_configured = _mask_secret(settings.ai_api_key_remote)
    return RuntimeSettingsResponse(
        enable_daily_sync_scheduler=settings.enable_daily_sync_scheduler,
        daily_sync_cron=settings.daily_sync_cron,
        worker_job_timeout_seconds=settings.worker_job_timeout_seconds,
        ai_model_default=settings.ai_model_default,
        ai_provider_mode=settings.ai_provider_mode,
        ai_base_url_remote=settings.ai_base_url_remote,
        ai_api_key_remote=masked_key,
        ai_api_key_remote_configured=key_configured,
        plugin_settings=[
            PluginSettingsGroupResponse(
                plugin_key=group["plugin_key"],
                plugin_name=group["plugin_name"],
                plugin_description=group.get("plugin_description"),
                capabilities=group.get("capabilities"),
                fields=[PluginSettingFieldResponse(**field) for field in group["fields"]],
            )
            for group in plugin_groups
        ],
    )


@router.get("/observability", response_model=ObservabilitySnapshot)
async def get_observability_snapshot(
    db: DBSession,
    period: str = Query("24h", pattern="^(24h|3d|7d|30d|90d)$"),
    force_refresh: bool = Query(False, alias="force_refresh"),
) -> ObservabilitySnapshot:
    service = ObservabilityService(db)
    return await service.snapshot(period=period, force_refresh=force_refresh)


@router.get("/settings", response_model=RuntimeSettingsResponse)
async def get_runtime_settings(db: DBSession) -> RuntimeSettingsResponse:
    service = AppSettingsService(db)
    library_service = MetadataLibrarySettingsService(db)
    settings = await service.get_runtime_settings()
    plugin_groups = await library_service.list_active_metadata_library_configs()
    return _build_runtime_settings_response(settings, plugin_groups)


@router.put("/settings", response_model=RuntimeSettingsResponse)
async def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    db: DBSession,
) -> RuntimeSettingsResponse:
    service = AppSettingsService(db)
    library_service = MetadataLibrarySettingsService(db)
    ai_api_key_remote = payload.ai_api_key_remote
    if ai_api_key_remote is not None and ai_api_key_remote.strip() == MASKED_SECRET_VALUE:
        ai_api_key_remote = None

    settings = await service.update_runtime_settings(
        enable_daily_sync_scheduler=payload.enable_daily_sync_scheduler,
        daily_sync_cron=payload.daily_sync_cron,
        worker_job_timeout_seconds=payload.worker_job_timeout_seconds,
        ai_model_default=payload.ai_model_default,
        ai_provider_mode=payload.ai_provider_mode,
        ai_base_url_remote=payload.ai_base_url_remote,
        ai_api_key_remote=ai_api_key_remote,
    )
    try:
        await library_service.update_metadata_library_configs(payload.plugin_settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await clear_observability_cache()
    plugin_groups = await library_service.list_active_metadata_library_configs()
    return _build_runtime_settings_response(settings, plugin_groups)
