"""Admin schemas."""

from pydantic import BaseModel, field_validator

from backend.services.cron_utils import validate_cron_expression


class RuntimeSettingsResponse(BaseModel):
    enable_daily_sync_scheduler: bool
    daily_sync_cron: str


class RuntimeSettingsUpdateRequest(BaseModel):
    enable_daily_sync_scheduler: bool | None = None
    daily_sync_cron: str | None = None

    @field_validator("daily_sync_cron")
    @classmethod
    def validate_cron(cls, value: str | None) -> str | None:
        if value is None:
            return value
        validate_cron_expression(value)
        return value.strip()

