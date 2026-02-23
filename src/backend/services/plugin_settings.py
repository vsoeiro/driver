"""Compatibility facade for legacy plugin settings imports.

Prefer importing from ``backend.services.metadata_libraries.settings``.
"""

from backend.services.metadata_libraries.settings import (
    COMICS_LIBRARY_KEY,
    METADATA_LIBRARY_PREFIX,
    PLUGIN_PREFIX,
    METADATA_LIBRARY_SETTINGS_REGISTRY as PLUGIN_SETTINGS_REGISTRY,
    ComicsRuntimeSettings as ComicRuntimeSettings,
    MetadataLibrarySettingFieldSpec as PluginSettingFieldSpec,
    MetadataLibrarySettingSpec as PluginSettingSpec,
    MetadataLibrarySettingsService as PluginSettingsService,
    setting_db_key,
)

__all__ = [
    "COMICS_LIBRARY_KEY",
    "METADATA_LIBRARY_PREFIX",
    "PLUGIN_PREFIX",
    "PLUGIN_SETTINGS_REGISTRY",
    "PluginSettingFieldSpec",
    "PluginSettingSpec",
    "ComicRuntimeSettings",
    "PluginSettingsService",
    "setting_db_key",
]

