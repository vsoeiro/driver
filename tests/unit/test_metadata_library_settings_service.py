import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import OperationalError

from backend.db.models import AppSetting
from backend.services.metadata_libraries import settings as library_settings
from backend.services.metadata_libraries.implementations.books.schema import BOOKS_LIBRARY_KEY
from backend.services.metadata_libraries.implementations.comics.schema import COMICS_LIBRARY_KEY


class _Result:
    def __init__(self, scalars=None):
        self._scalars = list(scalars or [])

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars))


def _setting(key, value):
    return AppSetting(key=key, value=value, description=f"{key} description")


@pytest.mark.asyncio
async def test_active_metadata_libraries_returns_empty_when_plugins_table_is_missing():
    service = library_settings.MetadataLibrarySettingsService(
        SimpleNamespace(
            execute=AsyncMock(
                side_effect=OperationalError("select", {}, Exception("no such table: metadata_plugins"))
            )
        )
    )

    assert await service._active_metadata_libraries() == []


@pytest.mark.asyncio
async def test_ensure_library_defaults_creates_missing_rows_and_commits():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Result(scalars=[])),
        add=Mock(),
        commit=AsyncMock(),
    )
    service = library_settings.MetadataLibrarySettingsService(session)
    spec = library_settings.METADATA_LIBRARY_SETTINGS_REGISTRY[COMICS_LIBRARY_KEY]

    rows = await service._ensure_library_defaults(spec)

    assert len(rows) == len(spec.fields)
    assert session.add.call_count == len(spec.fields)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_active_metadata_library_configs_builds_public_payload():
    service = library_settings.MetadataLibrarySettingsService(SimpleNamespace())
    spec = library_settings.METADATA_LIBRARY_SETTINGS_REGISTRY[COMICS_LIBRARY_KEY]
    rows = {
        library_settings.setting_db_key(COMICS_LIBRARY_KEY, field.key): _setting(
            library_settings.setting_db_key(COMICS_LIBRARY_KEY, field.key),
            library_settings.MetadataLibrarySettingsService._serialize_value(field, field.default),
        )
        for field in spec.fields
    }
    service._active_metadata_libraries = AsyncMock(
        return_value=[
            SimpleNamespace(
                key=COMICS_LIBRARY_KEY,
                name="",
                description=None,
            )
        ]
    )
    service._ensure_library_defaults = AsyncMock(return_value=rows)

    configs = await service.list_active_metadata_library_configs()

    assert len(configs) == 1
    config = configs[0]
    assert config["plugin_key"] == COMICS_LIBRARY_KEY
    assert config["plugin_name"] == "Comics Core"
    assert config["capabilities"]["actions"] == ["reindex_covers"]
    assert any(field["key"] == "cover_storage_target" for field in config["fields"])


@pytest.mark.asyncio
async def test_update_metadata_library_configs_validates_payload_and_persists_changes():
    session = SimpleNamespace(commit=AsyncMock())
    service = library_settings.MetadataLibrarySettingsService(session)
    spec = library_settings.METADATA_LIBRARY_SETTINGS_REGISTRY[COMICS_LIBRARY_KEY]
    rows = {
        library_settings.setting_db_key(COMICS_LIBRARY_KEY, field.key): _setting(
            library_settings.setting_db_key(COMICS_LIBRARY_KEY, field.key),
            library_settings.MetadataLibrarySettingsService._serialize_value(field, field.default),
        )
        for field in spec.fields
    }
    service._active_metadata_libraries = AsyncMock(return_value=[SimpleNamespace(key=COMICS_LIBRARY_KEY)])
    service._ensure_library_defaults = AsyncMock(return_value=rows)

    with pytest.raises(ValueError, match="Unknown metadata library settings key"):
        await service.update_metadata_library_configs({"unknown": {}})

    with pytest.raises(ValueError, match="must be active before updating settings"):
        service._active_metadata_libraries = AsyncMock(return_value=[SimpleNamespace(key=BOOKS_LIBRARY_KEY)])
        await service.update_metadata_library_configs({COMICS_LIBRARY_KEY: {}})

    service._active_metadata_libraries = AsyncMock(return_value=[SimpleNamespace(key=COMICS_LIBRARY_KEY)])
    with pytest.raises(ValueError, match="Unknown setting 'bad_field'"):
        await service.update_metadata_library_configs({COMICS_LIBRARY_KEY: {"bad_field": "x"}})

    await service.update_metadata_library_configs(
        {
            COMICS_LIBRARY_KEY: {
                "cover_max_width": 1024,
                "cover_storage_target": {
                    "account_id": " acc-1 ",
                    "folder_id": "",
                    "folder_path": "",
                },
                "cover_jpeg_quality_steps": "80,70",
            }
        }
    )

    assert rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_max_width")].value == "1024"
    assert json.loads(rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_storage_target")].value) == {
        "account_id": "acc-1",
        "folder_id": "root",
        "folder_path": "Root",
    }
    assert rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_jpeg_quality_steps")].value == "80,70"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_cover_runtime_settings_parses_values_and_applies_guards():
    service = library_settings.MetadataLibrarySettingsService(SimpleNamespace())
    spec = library_settings.METADATA_LIBRARY_SETTINGS_REGISTRY[COMICS_LIBRARY_KEY]
    rows = {}
    for field in spec.fields:
        db_key = library_settings.setting_db_key(COMICS_LIBRARY_KEY, field.key)
        rows[db_key] = _setting(
            db_key,
            library_settings.MetadataLibrarySettingsService._serialize_value(field, field.default),
        )

    rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_storage_target")].value = json.dumps(
        {"account_id": "acc-1", "folder_id": "", "folder_path": "Library"}
    )
    rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_storage_folder_name")].value = "  "
    rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_max_width")].value = "10"
    rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_max_height")].value = "20"
    rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_target_bytes")].value = "999"
    rows[library_settings.setting_db_key(COMICS_LIBRARY_KEY, "cover_jpeg_quality_steps")].value = "85,70,55"
    service._ensure_library_defaults = AsyncMock(return_value=rows)

    runtime = await service.get_comics_runtime_settings()

    assert runtime.storage_account_id == "acc-1"
    assert runtime.storage_parent_folder_id == "root"
    assert runtime.storage_folder_name == "__driver_comic_covers__"
    assert runtime.max_width == 64
    assert runtime.max_height == 64
    assert runtime.target_bytes == 10_000
    assert runtime.quality_steps == (85, 70, 55)


def test_metadata_library_settings_helpers_validate_and_parse_values():
    service = library_settings.MetadataLibrarySettingsService(SimpleNamespace())
    number_field = library_settings.MetadataLibrarySettingFieldSpec(
        key="cover_max_width",
        label="Width",
        input_type="number",
        minimum=100,
        maximum=2000,
        default=800,
    )
    text_field = library_settings.MetadataLibrarySettingFieldSpec(
        key="cover_jpeg_quality_steps",
        label="Quality",
        input_type="text",
        required=True,
        default="84,78",
    )
    folder_field = library_settings.MetadataLibrarySettingFieldSpec(
        key="cover_storage_target",
        label="Folder",
        input_type="folder_target",
        default={"account_id": "", "folder_id": "root", "folder_path": "Root"},
    )

    assert service._validate_value(number_field, 512) == 512
    assert service._validate_value(text_field, "80,70") == "80,70"
    assert service._validate_value(folder_field, {"account_id": " acc ", "folder_id": "", "folder_path": ""}) == {
        "account_id": "acc",
        "folder_id": "root",
        "folder_path": "Root",
    }
    assert library_settings.MetadataLibrarySettingsService._parse_value(number_field, "bad") == 800
    assert library_settings.MetadataLibrarySettingsService._parse_value(folder_field, "{bad") == folder_field.default
    assert library_settings.MetadataLibrarySettingsService._parse_quality_steps("90,80") == (90, 80)

    with pytest.raises(ValueError, match="cover_max_width must be >="):
        service._validate_value(number_field, 50)

    with pytest.raises(ValueError, match="cover_jpeg_quality_steps cannot be empty"):
        library_settings.MetadataLibrarySettingsService._parse_quality_steps("")
