"""Admin routes for runtime settings."""

from fastapi import APIRouter, HTTPException, status

from backend.api.dependencies import DBSession
from backend.schemas.admin import (
    ObservabilitySnapshot,
    PluginSettingFieldResponse,
    PluginSettingsGroupResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from backend.services.app_settings import AppSettingsService
from backend.services.observability import ObservabilityService
from backend.services.plugin_settings import PluginSettingsService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/observability", response_model=ObservabilitySnapshot)
async def get_observability_snapshot(db: DBSession) -> ObservabilitySnapshot:
    service = ObservabilityService(db)
    return await service.snapshot()


@router.get("/settings", response_model=RuntimeSettingsResponse)
async def get_runtime_settings(db: DBSession) -> RuntimeSettingsResponse:
    service = AppSettingsService(db)
    plugin_service = PluginSettingsService(db)
    settings = await service.get_runtime_settings()
    plugin_groups = await plugin_service.list_active_plugin_configs()
    return RuntimeSettingsResponse(
        enable_daily_sync_scheduler=settings.enable_daily_sync_scheduler,
        daily_sync_cron=settings.daily_sync_cron,
        worker_job_timeout_seconds=settings.worker_job_timeout_seconds,
        ai_enabled=settings.ai_enabled,
        ai_provider=settings.ai_provider,
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
        ai_temperature=settings.ai_temperature,
        ai_timeout_seconds=settings.ai_timeout_seconds,
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


@router.put("/settings", response_model=RuntimeSettingsResponse)
async def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    db: DBSession,
) -> RuntimeSettingsResponse:
    service = AppSettingsService(db)
    plugin_service = PluginSettingsService(db)
    settings = await service.update_runtime_settings(
        enable_daily_sync_scheduler=payload.enable_daily_sync_scheduler,
        daily_sync_cron=payload.daily_sync_cron,
        worker_job_timeout_seconds=payload.worker_job_timeout_seconds,
        ai_enabled=payload.ai_enabled,
        ai_provider=payload.ai_provider,
        ai_base_url=payload.ai_base_url,
        ai_model=payload.ai_model,
        ai_temperature=payload.ai_temperature,
        ai_timeout_seconds=payload.ai_timeout_seconds,
    )
    try:
        await plugin_service.update_plugin_configs(payload.plugin_settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    plugin_groups = await plugin_service.list_active_plugin_configs()
    return RuntimeSettingsResponse(
        enable_daily_sync_scheduler=settings.enable_daily_sync_scheduler,
        daily_sync_cron=settings.daily_sync_cron,
        worker_job_timeout_seconds=settings.worker_job_timeout_seconds,
        ai_enabled=settings.ai_enabled,
        ai_provider=settings.ai_provider,
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
        ai_temperature=settings.ai_temperature,
        ai_timeout_seconds=settings.ai_timeout_seconds,
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
