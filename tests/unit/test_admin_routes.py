from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.api.routes import admin as admin_routes
from backend.services.app_settings import RuntimeSettings


def test_mask_secret_and_build_runtime_settings_response():
    masked, configured = admin_routes._mask_secret(" secret ")
    assert masked == admin_routes.MASKED_SECRET_VALUE
    assert configured is True
    assert admin_routes._mask_secret("")[0] is None

    response = admin_routes._build_runtime_settings_response(
        RuntimeSettings(
            enable_daily_sync_scheduler=True,
            daily_sync_cron="0 3 * * *",
            worker_job_timeout_seconds=120,
            ai_model_default="gpt",
            ai_provider_mode="openai_compatible",
            ai_base_url_remote="https://example.test",
            ai_api_key_remote="secret",
        ),
        [
            {
                "plugin_key": "comics_core",
                "plugin_name": "Comics",
                "plugin_description": "desc",
                "capabilities": {"metadata": True},
                "fields": [{"key": "enabled", "label": "Enabled", "input_type": "boolean", "value": True}],
            }
        ],
    )

    assert response.ai_api_key_remote == admin_routes.MASKED_SECRET_VALUE
    assert response.ai_api_key_remote_configured is True
    assert response.plugin_settings[0].plugin_key == "comics_core"


@pytest.mark.asyncio
async def test_admin_routes_delegate_to_services(monkeypatch):
    settings_service = SimpleNamespace(
        get_runtime_settings=AsyncMock(
            return_value=RuntimeSettings(
                enable_daily_sync_scheduler=False,
                daily_sync_cron="0 0 * * *",
                worker_job_timeout_seconds=1800,
                ai_model_default="gpt",
                ai_provider_mode="local",
                ai_base_url_remote=None,
                ai_api_key_remote=None,
            )
        ),
        update_runtime_settings=AsyncMock(
            return_value=RuntimeSettings(
                enable_daily_sync_scheduler=True,
                daily_sync_cron="0 1 * * *",
                worker_job_timeout_seconds=60,
                ai_model_default="gpt-4o",
                ai_provider_mode="openai_compatible",
                ai_base_url_remote="https://example.test",
                ai_api_key_remote=None,
            )
        ),
    )
    library_service = SimpleNamespace(
        list_active_metadata_library_configs=AsyncMock(return_value=[]),
        update_metadata_library_configs=AsyncMock(return_value=None),
    )
    observability_service = SimpleNamespace(snapshot=AsyncMock(return_value="snapshot"))
    clear_cache = AsyncMock(return_value=None)

    monkeypatch.setattr(admin_routes, "AppSettingsService", lambda db: settings_service)
    monkeypatch.setattr(admin_routes, "MetadataLibrarySettingsService", lambda db: library_service)
    monkeypatch.setattr(admin_routes, "ObservabilityService", lambda db: observability_service)
    monkeypatch.setattr(admin_routes, "clear_observability_cache", clear_cache)

    assert await admin_routes.get_observability_snapshot(db=object(), period="7d", force_refresh=True) == "snapshot"
    runtime = await admin_routes.get_runtime_settings(db=object())
    assert runtime.ai_model_default == "gpt"

    payload = SimpleNamespace(
        enable_daily_sync_scheduler=True,
        daily_sync_cron="0 1 * * *",
        worker_job_timeout_seconds=60,
        ai_model_default="gpt-4o",
        ai_provider_mode="openai_compatible",
        ai_base_url_remote="https://example.test",
        ai_api_key_remote=admin_routes.MASKED_SECRET_VALUE,
        plugin_settings=[],
    )
    updated = await admin_routes.update_runtime_settings(payload, db=object())
    assert updated.ai_provider_mode == "openai_compatible"
    settings_service.update_runtime_settings.assert_awaited_once_with(
        enable_daily_sync_scheduler=True,
        daily_sync_cron="0 1 * * *",
        worker_job_timeout_seconds=60,
        ai_model_default="gpt-4o",
        ai_provider_mode="openai_compatible",
        ai_base_url_remote="https://example.test",
        ai_api_key_remote=None,
    )
    library_service.update_metadata_library_configs.assert_awaited_once_with([])
    clear_cache.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_runtime_settings_maps_plugin_validation_error(monkeypatch):
    settings_service = SimpleNamespace(
        update_runtime_settings=AsyncMock(
            return_value=RuntimeSettings(
                enable_daily_sync_scheduler=True,
                daily_sync_cron="0 1 * * *",
                worker_job_timeout_seconds=60,
                ai_model_default="gpt-4o",
                ai_provider_mode="local",
                ai_base_url_remote=None,
                ai_api_key_remote=None,
            )
        )
    )
    library_service = SimpleNamespace(
        update_metadata_library_configs=AsyncMock(side_effect=ValueError("invalid plugin settings")),
    )
    monkeypatch.setattr(admin_routes, "AppSettingsService", lambda db: settings_service)
    monkeypatch.setattr(admin_routes, "MetadataLibrarySettingsService", lambda db: library_service)

    with pytest.raises(HTTPException) as exc:
        await admin_routes.update_runtime_settings(
            SimpleNamespace(
                enable_daily_sync_scheduler=True,
                daily_sync_cron="0 1 * * *",
                worker_job_timeout_seconds=60,
                ai_model_default="gpt-4o",
                ai_provider_mode="local",
                ai_base_url_remote=None,
                ai_api_key_remote=None,
                plugin_settings=[],
            ),
            db=object(),
        )

    assert exc.value.status_code == 400
    assert "invalid plugin settings" in exc.value.detail
