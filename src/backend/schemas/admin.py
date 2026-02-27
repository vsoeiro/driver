"""Admin schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

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
    worker_job_timeout_seconds: int
    ai_model_default: str
    ai_provider_mode: str
    ai_base_url_remote: str | None = None
    ai_api_key_remote: str | None = None
    plugin_settings: list[PluginSettingsGroupResponse] = []


class RuntimeSettingsUpdateRequest(BaseModel):
    enable_daily_sync_scheduler: bool | None = None
    daily_sync_cron: str | None = None
    worker_job_timeout_seconds: int | None = None
    ai_model_default: str | None = None
    ai_provider_mode: str | None = None
    ai_base_url_remote: str | None = None
    ai_api_key_remote: str | None = None
    plugin_settings: dict[str, dict[str, Any]] | None = None

    @field_validator("daily_sync_cron")
    @classmethod
    def validate_cron(cls, value: str | None) -> str | None:
        if value is None:
            return value
        validate_cron_expression(value)
        return value.strip()

    @field_validator("worker_job_timeout_seconds")
    @classmethod
    def validate_worker_timeout(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("worker_job_timeout_seconds must be greater than 0")
        return value

    @field_validator("ai_model_default")
    @classmethod
    def validate_ai_model_default(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("ai_model_default cannot be empty")
        return normalized

    @field_validator("ai_provider_mode")
    @classmethod
    def validate_ai_provider_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized == "remote":
            normalized = "openai_compatible"
        elif normalized == "hybrid":
            normalized = "local"
        if normalized not in {"local", "openai_compatible", "gemini"}:
            raise ValueError("ai_provider_mode must be one of: local, openai_compatible, gemini")
        return normalized

    @field_validator("ai_base_url_remote", "ai_api_key_remote")
    @classmethod
    def normalize_optional_ai_fields(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip()


class IntegrationHealthStatus(BaseModel):
    key: str
    label: str
    status: str
    detail: str | None = None


class ObservabilityAlert(BaseModel):
    severity: str
    code: str
    message: str
    created_at: datetime


class DeadLetterJobSummary(BaseModel):
    id: UUID
    type: str
    dead_lettered_at: datetime | None = None
    dead_letter_reason: str | None = None
    retry_count: int
    max_retries: int


class ProviderRequestUsage(BaseModel):
    provider: str
    provider_label: str
    window_seconds: int
    max_requests: int
    requests_in_window: int
    utilization_ratio: float
    docs_url: str | None = None
    notes: str | None = None
    total_requests_since_start: int = 0
    successful_responses: int = 0
    throttled_responses: int = 0
    client_error_responses: int = 0
    server_error_responses: int = 0
    timeout_errors: int = 0
    connection_errors: int = 0
    last_request_at: datetime | None = None


class ObservabilitySnapshot(BaseModel):
    generated_at: datetime
    period_key: str = "24h"
    period_label: str = "24h"
    period_hours: int = 24
    queue_depth: int
    pending_jobs: int
    running_jobs: int
    retry_scheduled_jobs: int
    throughput_last_hour: int
    throughput_window: int
    throughput_last_24h: int
    success_rate_window: float
    success_rate_last_24h: float
    avg_duration_seconds_window: float | None = None
    avg_duration_seconds_last_24h: float | None = None
    p95_duration_seconds_window: float | None = None
    p95_duration_seconds_last_24h: float | None = None
    dead_letter_jobs_window: int
    dead_letter_jobs_24h: int
    metrics_total_window: int = 0
    metrics_success_window: int = 0
    metrics_failed_window: int = 0
    metrics_skipped_window: int = 0
    metrics_total_24h: int = 0
    metrics_success_24h: int = 0
    metrics_failed_24h: int = 0
    metrics_skipped_24h: int = 0
    cache_hit: bool = False
    cache_ttl_seconds: int = 0
    cache_expires_at: datetime | None = None
    recent_alerts: list[ObservabilityAlert] = []
    integration_health: list[IntegrationHealthStatus] = []
    dead_letter_jobs: list[DeadLetterJobSummary] = []
    provider_request_usage: list[ProviderRequestUsage] = []
