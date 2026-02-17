"""Persisted runtime settings service."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.models import AppSetting
from backend.services.cron_utils import validate_cron_expression


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class RuntimeSettings:
    enable_daily_sync_scheduler: bool
    daily_sync_cron: str
    worker_job_timeout_seconds: int
    ai_enabled: bool
    ai_provider: str
    ai_base_url: str
    ai_model: str
    ai_temperature: float
    ai_timeout_seconds: int


class AppSettingsService:
    """Read and mutate runtime settings persisted in database."""

    ENABLE_DAILY_SYNC_KEY = "enable_daily_sync_scheduler"
    DAILY_SYNC_CRON_KEY = "daily_sync_cron"
    WORKER_JOB_TIMEOUT_SECONDS_KEY = "worker_job_timeout_seconds"
    AI_ENABLED_KEY = "ai_enabled"
    AI_PROVIDER_KEY = "ai_provider"
    AI_BASE_URL_KEY = "ai_base_url"
    AI_MODEL_KEY = "ai_model"
    AI_TEMPERATURE_KEY = "ai_temperature"
    AI_TIMEOUT_SECONDS_KEY = "ai_timeout_seconds"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_defaults(self) -> None:
        defaults = self._default_values()
        keys = tuple(defaults.keys())
        result = await self.session.execute(
            select(AppSetting.key).where(AppSetting.key.in_(keys))
        )
        existing = set(result.scalars().all())
        changed = False
        for key, (value, description) in defaults.items():
            if key in existing:
                continue
            self.session.add(AppSetting(key=key, value=value, description=description))
            changed = True
        if changed:
            await self.session.commit()

    async def get_runtime_settings(self) -> RuntimeSettings:
        await self.ensure_defaults()
        rows = await self._get_settings_map()
        cron_expr = rows[self.DAILY_SYNC_CRON_KEY].value
        validate_cron_expression(cron_expr)
        ai_provider = rows[self.AI_PROVIDER_KEY].value.strip()
        if ai_provider not in {"ollama", "llama_cpp"}:
            ai_provider = "ollama"
        ai_temperature = self._parse_float(rows[self.AI_TEMPERATURE_KEY].value, default=0.1)
        ai_timeout_seconds = self._parse_int(rows[self.AI_TIMEOUT_SECONDS_KEY].value, default=120)
        return RuntimeSettings(
            enable_daily_sync_scheduler=_to_bool(rows[self.ENABLE_DAILY_SYNC_KEY].value),
            daily_sync_cron=cron_expr,
            worker_job_timeout_seconds=max(
                1,
                self._parse_int(rows[self.WORKER_JOB_TIMEOUT_SECONDS_KEY].value, default=1800),
            ),
            ai_enabled=_to_bool(rows[self.AI_ENABLED_KEY].value),
            ai_provider=ai_provider,
            ai_base_url=rows[self.AI_BASE_URL_KEY].value.strip(),
            ai_model=rows[self.AI_MODEL_KEY].value.strip(),
            ai_temperature=max(0.0, min(2.0, ai_temperature)),
            ai_timeout_seconds=max(1, ai_timeout_seconds),
        )

    async def update_runtime_settings(
        self,
        *,
        enable_daily_sync_scheduler: bool | None = None,
        daily_sync_cron: str | None = None,
        worker_job_timeout_seconds: int | None = None,
        ai_enabled: bool | None = None,
        ai_provider: str | None = None,
        ai_base_url: str | None = None,
        ai_model: str | None = None,
        ai_temperature: float | None = None,
        ai_timeout_seconds: int | None = None,
    ) -> RuntimeSettings:
        await self.ensure_defaults()
        rows = await self._get_settings_map()

        if enable_daily_sync_scheduler is not None:
            rows[self.ENABLE_DAILY_SYNC_KEY].value = "true" if enable_daily_sync_scheduler else "false"

        if daily_sync_cron is not None:
            cron_expr = daily_sync_cron.strip()
            validate_cron_expression(cron_expr)
            rows[self.DAILY_SYNC_CRON_KEY].value = cron_expr
        if worker_job_timeout_seconds is not None:
            if worker_job_timeout_seconds <= 0:
                raise ValueError("worker_job_timeout_seconds must be greater than 0")
            rows[self.WORKER_JOB_TIMEOUT_SECONDS_KEY].value = str(worker_job_timeout_seconds)

        if ai_enabled is not None:
            rows[self.AI_ENABLED_KEY].value = "true" if ai_enabled else "false"
        if ai_provider is not None:
            provider = ai_provider.strip()
            if provider not in {"ollama", "llama_cpp"}:
                raise ValueError("ai_provider must be 'ollama' or 'llama_cpp'")
            rows[self.AI_PROVIDER_KEY].value = provider
        if ai_base_url is not None:
            rows[self.AI_BASE_URL_KEY].value = ai_base_url.strip()
        if ai_model is not None:
            rows[self.AI_MODEL_KEY].value = ai_model.strip()
        if ai_temperature is not None:
            if not 0 <= ai_temperature <= 2:
                raise ValueError("ai_temperature must be between 0 and 2")
            rows[self.AI_TEMPERATURE_KEY].value = str(ai_temperature)
        if ai_timeout_seconds is not None:
            if ai_timeout_seconds <= 0:
                raise ValueError("ai_timeout_seconds must be greater than 0")
            rows[self.AI_TIMEOUT_SECONDS_KEY].value = str(ai_timeout_seconds)

        runtime = RuntimeSettings(
            enable_daily_sync_scheduler=_to_bool(rows[self.ENABLE_DAILY_SYNC_KEY].value),
            daily_sync_cron=rows[self.DAILY_SYNC_CRON_KEY].value,
            worker_job_timeout_seconds=self._parse_int(
                rows[self.WORKER_JOB_TIMEOUT_SECONDS_KEY].value,
                default=1800,
            ),
            ai_enabled=_to_bool(rows[self.AI_ENABLED_KEY].value),
            ai_provider=rows[self.AI_PROVIDER_KEY].value.strip(),
            ai_base_url=rows[self.AI_BASE_URL_KEY].value.strip(),
            ai_model=rows[self.AI_MODEL_KEY].value.strip(),
            ai_temperature=self._parse_float(rows[self.AI_TEMPERATURE_KEY].value, default=0.1),
            ai_timeout_seconds=self._parse_int(rows[self.AI_TIMEOUT_SECONDS_KEY].value, default=120),
        )
        await self.session.commit()
        return runtime

    async def _get_settings_map(self) -> dict[str, AppSetting]:
        result = await self.session.execute(
            select(AppSetting).where(
                AppSetting.key.in_(
                    (
                        self.ENABLE_DAILY_SYNC_KEY,
                        self.DAILY_SYNC_CRON_KEY,
                        self.WORKER_JOB_TIMEOUT_SECONDS_KEY,
                        self.AI_ENABLED_KEY,
                        self.AI_PROVIDER_KEY,
                        self.AI_BASE_URL_KEY,
                        self.AI_MODEL_KEY,
                        self.AI_TEMPERATURE_KEY,
                        self.AI_TIMEOUT_SECONDS_KEY,
                    )
                )
            )
        )
        rows = {row.key: row for row in result.scalars().all()}
        for key, (value, description) in self._default_values().items():
            if key not in rows:
                row = AppSetting(key=key, value=value, description=description)
                self.session.add(row)
                rows[key] = row
        return rows

    @staticmethod
    def _default_values() -> dict[str, tuple[str, str]]:
        settings = get_settings()
        return {
            AppSettingsService.ENABLE_DAILY_SYNC_KEY: (
                "true" if settings.enable_daily_sync_scheduler else "false",
                "Enable/disable the automatic daily sync scheduler.",
            ),
            AppSettingsService.DAILY_SYNC_CRON_KEY: (
                settings.daily_sync_cron,
                "Cron expression (5 fields) for scheduler frequency.",
            ),
            AppSettingsService.WORKER_JOB_TIMEOUT_SECONDS_KEY: (
                str(settings.worker_job_timeout_seconds),
                "ARQ worker timeout in seconds for one job execution.",
            ),
            AppSettingsService.AI_ENABLED_KEY: (
                "true" if settings.ai_enabled else "false",
                "Enable/disable AI features.",
            ),
            AppSettingsService.AI_PROVIDER_KEY: (
                settings.ai_provider,
                "AI provider: ollama or llama_cpp.",
            ),
            AppSettingsService.AI_BASE_URL_KEY: (
                settings.ai_base_url,
                "Base URL for local AI server.",
            ),
            AppSettingsService.AI_MODEL_KEY: (
                settings.ai_model,
                "Model identifier used for inference.",
            ),
            AppSettingsService.AI_TEMPERATURE_KEY: (
                str(settings.ai_temperature),
                "Sampling temperature (0..2).",
            ),
            AppSettingsService.AI_TIMEOUT_SECONDS_KEY: (
                str(settings.ai_timeout_seconds),
                "Request timeout for model inference.",
            ),
        }

    @staticmethod
    def _parse_float(value: str, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_int(value: str, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
