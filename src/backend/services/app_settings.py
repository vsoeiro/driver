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
    ai_model_default: str
    ai_provider_mode: str
    ai_base_url_remote: str | None
    ai_api_key_remote: str | None


class AppSettingsService:
    """Read and mutate runtime settings persisted in database."""

    ENABLE_DAILY_SYNC_KEY = "enable_daily_sync_scheduler"
    DAILY_SYNC_CRON_KEY = "daily_sync_cron"
    WORKER_JOB_TIMEOUT_SECONDS_KEY = "worker_job_timeout_seconds"
    AI_MODEL_DEFAULT_KEY = "ai_model_default"
    AI_PROVIDER_MODE_KEY = "ai_provider_mode"
    AI_BASE_URL_REMOTE_KEY = "ai_base_url_remote"
    AI_API_KEY_REMOTE_KEY = "ai_api_key_remote"

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
        settings = get_settings()
        rows = await self._get_settings_map()
        cron_expr = rows[self.DAILY_SYNC_CRON_KEY].value
        validate_cron_expression(cron_expr)
        return RuntimeSettings(
            enable_daily_sync_scheduler=_to_bool(rows[self.ENABLE_DAILY_SYNC_KEY].value),
            daily_sync_cron=cron_expr,
            worker_job_timeout_seconds=max(
                1,
                self._parse_int(rows[self.WORKER_JOB_TIMEOUT_SECONDS_KEY].value, default=1800),
            ),
            ai_model_default=str(rows[self.AI_MODEL_DEFAULT_KEY].value or settings.ai_model_default).strip() or settings.ai_model_default,
            ai_provider_mode=self._normalize_ai_provider_mode(
                rows[self.AI_PROVIDER_MODE_KEY].value,
                fallback=settings.ai_provider_mode,
            ),
            ai_base_url_remote=self._normalize_optional_string(rows[self.AI_BASE_URL_REMOTE_KEY].value),
            ai_api_key_remote=self._normalize_optional_string(rows[self.AI_API_KEY_REMOTE_KEY].value),
        )

    async def update_runtime_settings(
        self,
        *,
        enable_daily_sync_scheduler: bool | None = None,
        daily_sync_cron: str | None = None,
        worker_job_timeout_seconds: int | None = None,
        ai_model_default: str | None = None,
        ai_provider_mode: str | None = None,
        ai_base_url_remote: str | None = None,
        ai_api_key_remote: str | None = None,
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

        if ai_model_default is not None:
            model_name = ai_model_default.strip()
            if not model_name:
                raise ValueError("ai_model_default cannot be empty")
            rows[self.AI_MODEL_DEFAULT_KEY].value = model_name

        if ai_provider_mode is not None:
            rows[self.AI_PROVIDER_MODE_KEY].value = self._normalize_ai_provider_mode(
                ai_provider_mode,
                fallback=get_settings().ai_provider_mode,
            )

        if ai_base_url_remote is not None:
            rows[self.AI_BASE_URL_REMOTE_KEY].value = ai_base_url_remote.strip()

        if ai_api_key_remote is not None:
            rows[self.AI_API_KEY_REMOTE_KEY].value = ai_api_key_remote.strip()

        runtime = RuntimeSettings(
            enable_daily_sync_scheduler=_to_bool(rows[self.ENABLE_DAILY_SYNC_KEY].value),
            daily_sync_cron=rows[self.DAILY_SYNC_CRON_KEY].value,
            worker_job_timeout_seconds=self._parse_int(
                rows[self.WORKER_JOB_TIMEOUT_SECONDS_KEY].value,
                default=1800,
            ),
            ai_model_default=str(rows[self.AI_MODEL_DEFAULT_KEY].value or "").strip() or get_settings().ai_model_default,
            ai_provider_mode=self._normalize_ai_provider_mode(
                rows[self.AI_PROVIDER_MODE_KEY].value,
                fallback=get_settings().ai_provider_mode,
            ),
            ai_base_url_remote=self._normalize_optional_string(rows[self.AI_BASE_URL_REMOTE_KEY].value),
            ai_api_key_remote=self._normalize_optional_string(rows[self.AI_API_KEY_REMOTE_KEY].value),
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
                        self.AI_MODEL_DEFAULT_KEY,
                        self.AI_PROVIDER_MODE_KEY,
                        self.AI_BASE_URL_REMOTE_KEY,
                        self.AI_API_KEY_REMOTE_KEY,
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
            AppSettingsService.AI_MODEL_DEFAULT_KEY: (
                settings.ai_model_default,
                "Default LLM model name used by AI assistant (local/openai-compatible providers).",
            ),
            AppSettingsService.AI_PROVIDER_MODE_KEY: (
                settings.ai_provider_mode,
                "AI provider mode: local, openai_compatible or gemini.",
            ),
            AppSettingsService.AI_BASE_URL_REMOTE_KEY: (
                settings.ai_base_url_remote or "",
                "OpenAI-compatible base URL used by openai_compatible provider mode.",
            ),
            AppSettingsService.AI_API_KEY_REMOTE_KEY: (
                settings.ai_api_key_remote or "",
                "API key used for openai_compatible provider.",
            ),
        }

    @staticmethod
    def _parse_int(value: str, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_optional_string(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _normalize_ai_provider_mode(value: str | None, *, fallback: str) -> str:
        normalized = str(value or fallback).strip().lower()
        if normalized == "remote":
            normalized = "openai_compatible"
        elif normalized == "hybrid":
            normalized = "local"
        if normalized not in {"local", "openai_compatible", "gemini"}:
            normalized = str(fallback or "local").strip().lower()
        if normalized == "remote":
            normalized = "openai_compatible"
        elif normalized == "hybrid":
            normalized = "local"
        if normalized not in {"local", "openai_compatible", "gemini"}:
            normalized = "local"
        return normalized
