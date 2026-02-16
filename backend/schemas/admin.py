"""Admin schemas."""

from typing import Any

from pydantic import BaseModel, field_validator

from backend.services.cron_utils import validate_cron_expression


class PluginSettingFieldResponse(BaseModel):
    key: str
    label: str
    input_type: str
    description: str | None = None
    required: bool = False
    minimum: int | None = None
    maximum: int | None = None
    placeholder: str | None = None
    account_field_key: str | None = None
    value: Any = None


class PluginSettingsGroupResponse(BaseModel):
    plugin_key: str
    plugin_name: str
    plugin_description: str | None = None
    capabilities: dict[str, Any] | None = None
    fields: list[PluginSettingFieldResponse]


class RuntimeSettingsResponse(BaseModel):
    enable_daily_sync_scheduler: bool
    daily_sync_cron: str
    ai_enabled: bool
    ai_provider: str
    ai_base_url: str
    ai_model: str
    ai_temperature: float
    ai_timeout_seconds: int
    plugin_settings: list[PluginSettingsGroupResponse] = []


class RuntimeSettingsUpdateRequest(BaseModel):
    enable_daily_sync_scheduler: bool | None = None
    daily_sync_cron: str | None = None
    ai_enabled: bool | None = None
    ai_provider: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_temperature: float | None = None
    ai_timeout_seconds: int | None = None
    plugin_settings: dict[str, dict[str, Any]] | None = None

    @field_validator("daily_sync_cron")
    @classmethod
    def validate_cron(cls, value: str | None) -> str | None:
        if value is None:
            return value
        validate_cron_expression(value)
        return value.strip()

    @field_validator("ai_provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return value
        provider = value.strip()
        if provider not in {"ollama", "llama_cpp"}:
            raise ValueError("ai_provider must be 'ollama' or 'llama_cpp'")
        return provider

    @field_validator("ai_temperature")
    @classmethod
    def validate_temperature(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not 0 <= value <= 2:
            raise ValueError("ai_temperature must be between 0 and 2")
        return value

    @field_validator("ai_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("ai_timeout_seconds must be greater than 0")
        return value
