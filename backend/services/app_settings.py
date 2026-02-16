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


class AppSettingsService:
    """Read and mutate runtime settings persisted in database."""

    ENABLE_DAILY_SYNC_KEY = "enable_daily_sync_scheduler"
    DAILY_SYNC_CRON_KEY = "daily_sync_cron"

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
        return RuntimeSettings(
            enable_daily_sync_scheduler=_to_bool(rows[self.ENABLE_DAILY_SYNC_KEY].value),
            daily_sync_cron=cron_expr,
        )

    async def update_runtime_settings(
        self,
        *,
        enable_daily_sync_scheduler: bool | None = None,
        daily_sync_cron: str | None = None,
    ) -> RuntimeSettings:
        await self.ensure_defaults()
        rows = await self._get_settings_map()

        if enable_daily_sync_scheduler is not None:
            rows[self.ENABLE_DAILY_SYNC_KEY].value = "true" if enable_daily_sync_scheduler else "false"

        if daily_sync_cron is not None:
            cron_expr = daily_sync_cron.strip()
            validate_cron_expression(cron_expr)
            rows[self.DAILY_SYNC_CRON_KEY].value = cron_expr

        return RuntimeSettings(
            enable_daily_sync_scheduler=_to_bool(rows[self.ENABLE_DAILY_SYNC_KEY].value),
            daily_sync_cron=rows[self.DAILY_SYNC_CRON_KEY].value,
        )

    async def _get_settings_map(self) -> dict[str, AppSetting]:
        result = await self.session.execute(
            select(AppSetting).where(
                AppSetting.key.in_(
                    (
                        self.ENABLE_DAILY_SYNC_KEY,
                        self.DAILY_SYNC_CRON_KEY,
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
        }

