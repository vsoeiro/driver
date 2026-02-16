"""Admin routes for runtime settings."""

from fastapi import APIRouter

from backend.api.dependencies import DBSession
from backend.schemas.admin import RuntimeSettingsResponse, RuntimeSettingsUpdateRequest
from backend.services.app_settings import AppSettingsService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/settings", response_model=RuntimeSettingsResponse)
async def get_runtime_settings(db: DBSession) -> RuntimeSettingsResponse:
    service = AppSettingsService(db)
    settings = await service.get_runtime_settings()
    return RuntimeSettingsResponse(
        enable_daily_sync_scheduler=settings.enable_daily_sync_scheduler,
        daily_sync_cron=settings.daily_sync_cron,
    )


@router.put("/settings", response_model=RuntimeSettingsResponse)
async def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    db: DBSession,
) -> RuntimeSettingsResponse:
    service = AppSettingsService(db)
    settings = await service.update_runtime_settings(
        enable_daily_sync_scheduler=payload.enable_daily_sync_scheduler,
        daily_sync_cron=payload.daily_sync_cron,
    )
    return RuntimeSettingsResponse(
        enable_daily_sync_scheduler=settings.enable_daily_sync_scheduler,
        daily_sync_cron=settings.daily_sync_cron,
    )

