from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.db.models import AppSetting
from backend.services import app_settings as app_settings_module


class _Result:
    def __init__(self, scalars=None):
        self._scalars = list(scalars or [])

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars))


def _config(**overrides):
    values = {
        "enable_daily_sync_scheduler": False,
        "daily_sync_cron": "0 3 * * *",
        "worker_job_timeout_seconds": 1800,
        "ai_model_default": "llama3",
        "ai_provider_mode": "local",
        "ai_base_url_remote": None,
        "ai_api_key_remote": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _row(key, value):
    return AppSetting(key=key, value=value, description=f"{key} description")


@pytest.mark.asyncio
async def test_ensure_defaults_adds_missing_rows_and_commits(monkeypatch):
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=_Result(scalars=[app_settings_module.AppSettingsService.ENABLE_DAILY_SYNC_KEY])
        ),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(app_settings_module, "get_settings", lambda: _config())

    service = app_settings_module.AppSettingsService(session)
    await service.ensure_defaults()

    assert session.add.call_count == 6
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_runtime_settings_normalizes_persisted_values(monkeypatch):
    service = app_settings_module.AppSettingsService(
        SimpleNamespace(
            execute=AsyncMock(
                return_value=_Result(
                    scalars=[
                        _row(service_key, value)
                        for service_key, value in [
                            (app_settings_module.AppSettingsService.ENABLE_DAILY_SYNC_KEY, "yes"),
                            (app_settings_module.AppSettingsService.DAILY_SYNC_CRON_KEY, "*/15 * * * *"),
                            (app_settings_module.AppSettingsService.WORKER_JOB_TIMEOUT_SECONDS_KEY, "0"),
                            (app_settings_module.AppSettingsService.AI_MODEL_DEFAULT_KEY, ""),
                            (app_settings_module.AppSettingsService.AI_PROVIDER_MODE_KEY, "remote"),
                            (app_settings_module.AppSettingsService.AI_BASE_URL_REMOTE_KEY, " https://api.example.test "),
                            (app_settings_module.AppSettingsService.AI_API_KEY_REMOTE_KEY, " "),
                        ]
                    ]
                )
            ),
            add=Mock(),
            commit=AsyncMock(),
        )
    )
    service.ensure_defaults = AsyncMock()
    validate_cron_mock = Mock()
    monkeypatch.setattr(app_settings_module, "validate_cron_expression", validate_cron_mock)
    monkeypatch.setattr(app_settings_module, "get_settings", lambda: _config(ai_model_default="fallback-model", ai_provider_mode="local"))

    runtime = await service.get_runtime_settings()

    assert runtime.enable_daily_sync_scheduler is True
    assert runtime.daily_sync_cron == "*/15 * * * *"
    assert runtime.worker_job_timeout_seconds == 1
    assert runtime.ai_model_default == "fallback-model"
    assert runtime.ai_provider_mode == "openai_compatible"
    assert runtime.ai_base_url_remote == "https://api.example.test"
    assert runtime.ai_api_key_remote is None
    validate_cron_mock.assert_called_once_with("*/15 * * * *")


@pytest.mark.asyncio
async def test_update_runtime_settings_mutates_rows_and_validates_inputs(monkeypatch):
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=_Result(
                scalars=[
                    _row(app_settings_module.AppSettingsService.ENABLE_DAILY_SYNC_KEY, "false"),
                    _row(app_settings_module.AppSettingsService.DAILY_SYNC_CRON_KEY, "0 3 * * *"),
                    _row(app_settings_module.AppSettingsService.WORKER_JOB_TIMEOUT_SECONDS_KEY, "1800"),
                    _row(app_settings_module.AppSettingsService.AI_MODEL_DEFAULT_KEY, "llama3"),
                    _row(app_settings_module.AppSettingsService.AI_PROVIDER_MODE_KEY, "local"),
                    _row(app_settings_module.AppSettingsService.AI_BASE_URL_REMOTE_KEY, ""),
                    _row(app_settings_module.AppSettingsService.AI_API_KEY_REMOTE_KEY, ""),
                ]
            )
        ),
        add=Mock(),
        commit=AsyncMock(),
    )
    service = app_settings_module.AppSettingsService(session)
    service.ensure_defaults = AsyncMock()
    validate_cron_mock = Mock()
    monkeypatch.setattr(app_settings_module, "validate_cron_expression", validate_cron_mock)
    monkeypatch.setattr(app_settings_module, "get_settings", lambda: _config(ai_provider_mode="gemini"))

    runtime = await service.update_runtime_settings(
        enable_daily_sync_scheduler=True,
        daily_sync_cron="0 6 * * *",
        worker_job_timeout_seconds=900,
        ai_model_default="gpt-4.1",
        ai_provider_mode="hybrid",
        ai_base_url_remote=" https://remote.example.test ",
        ai_api_key_remote=" secret ",
    )

    assert runtime.enable_daily_sync_scheduler is True
    assert runtime.daily_sync_cron == "0 6 * * *"
    assert runtime.worker_job_timeout_seconds == 900
    assert runtime.ai_model_default == "gpt-4.1"
    assert runtime.ai_provider_mode == "local"
    assert runtime.ai_base_url_remote == "https://remote.example.test"
    assert runtime.ai_api_key_remote == "secret"
    validate_cron_mock.assert_called_once_with("0 6 * * *")
    session.commit.assert_awaited_once()

    with pytest.raises(ValueError, match="worker_job_timeout_seconds must be greater than 0"):
        await service.update_runtime_settings(worker_job_timeout_seconds=0)

    with pytest.raises(ValueError, match="ai_model_default cannot be empty"):
        await service.update_runtime_settings(ai_model_default="   ")


def test_app_settings_helpers_normalize_booleans_and_provider_modes():
    assert app_settings_module._to_bool("yes") is True
    assert app_settings_module._to_bool("0") is False
    assert app_settings_module.AppSettingsService._parse_int("oops", default=7) == 7
    assert app_settings_module.AppSettingsService._normalize_optional_string("   ") is None
    assert (
        app_settings_module.AppSettingsService._normalize_ai_provider_mode("remote", fallback="local")
        == "openai_compatible"
    )
    assert (
        app_settings_module.AppSettingsService._normalize_ai_provider_mode("invalid", fallback="invalid")
        == "local"
    )
