"""Application configuration settings.

This module provides configuration management through Pydantic Settings,
loading values from environment variables and .env files.
"""

from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv
from backend.services.cron_utils import validate_cron_expression

PROJECT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_DIR / ".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes
    ----------
    microsoft_client_id : str
        Azure AD application client ID.
    microsoft_client_secret : str
        Azure AD application client secret.
    microsoft_tenant_id : str
        Azure AD tenant ID. Use 'common' for multi-tenant apps.
    app_secret_key : str
        Secret key for JWT signing.
    token_encryption_key : str
        Base64-encoded 32-byte key for Fernet encryption.
    database_url : str
        PostgreSQL connection string with asyncpg driver.
    host : str
        Server host address.
    port : int
        Server port number.
    debug : bool
        Enable debug mode.
    """

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    microsoft_client_id: str = Field(alias="MS_CLIENT_ID")
    microsoft_client_secret: str = Field(alias="MS_CLIENT_SECRET")
    microsoft_tenant_id: str = Field(default="common", alias="MS_TENANT_ID")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")

    app_secret_key: str = Field(alias="SECRET_KEY")
    token_encryption_key: str = Field(alias="ENCRYPTION_KEY")

    database_url: str = Field(alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=0, alias="DB_MAX_OVERFLOW")
    db_pool_timeout_seconds: int = Field(default=30, alias="DB_POOL_TIMEOUT_SECONDS")
    db_pool_recycle_seconds: int = Field(default=1800, alias="DB_POOL_RECYCLE_SECONDS")

    redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/microsoft/callback", alias="MS_REDIRECT_URI")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/auth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    enable_daily_sync_scheduler: bool = Field(default=True, alias="ENABLE_DAILY_SYNC_SCHEDULER")
    daily_sync_cron: str | None = Field(default=None, alias="DAILY_SYNC_CRON")
    daily_sync_hour: int | None = Field(default=None, alias="DAILY_SYNC_HOUR")
    daily_sync_minute: int | None = Field(default=None, alias="DAILY_SYNC_MINUTE")
    comic_cover_storage_account_id: str | None = Field(default=None, alias="COMIC_COVER_STORAGE_ACCOUNT_ID")
    comic_cover_storage_parent_folder_id: str = Field(default="root", alias="COMIC_COVER_STORAGE_PARENT_FOLDER_ID")
    comic_cover_storage_folder_name: str = Field(
        default="__driver_comic_covers__",
        alias="COMIC_COVER_STORAGE_FOLDER_NAME",
    )
    comic_cover_max_width: int = Field(default=700, alias="COMIC_COVER_MAX_WIDTH")
    comic_cover_max_height: int = Field(default=1050, alias="COMIC_COVER_MAX_HEIGHT")
    comic_cover_target_bytes: int = Field(default=250000, alias="COMIC_COVER_TARGET_BYTES")
    comic_cover_jpeg_quality_steps: str = Field(
        default="84,78,72,66,60",
        alias="COMIC_COVER_JPEG_QUALITY_STEPS",
    )
    comic_rar_tools_dir: str | None = Field(default=None, alias="COMIC_RAR_TOOLS_DIR")
    comic_rar_tool_path: str | None = Field(default=None, alias="COMIC_RAR_TOOL_PATH")
    comic_rar_tool_auto_install: bool = Field(default=True, alias="COMIC_RAR_TOOL_AUTO_INSTALL")
    comic_rar_tool_download_url: str | None = Field(default=None, alias="COMIC_RAR_TOOL_DOWNLOAD_URL")
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")
    redis_queue_name: str = Field(default="driver:jobs", alias="REDIS_QUEUE_NAME")
    worker_concurrency: int = Field(default=8, alias="WORKER_CONCURRENCY")
    worker_job_timeout_seconds: int = Field(default=1800, alias="WORKER_JOB_TIMEOUT_SECONDS")

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        if self.database_url.startswith("sqlite:///") and "aiosqlite" not in self.database_url:
            self.database_url = self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        if self.db_pool_size <= 0:
            raise ValueError("DB_POOL_SIZE must be greater than 0")
        if self.db_max_overflow < 0:
            raise ValueError("DB_MAX_OVERFLOW must be greater than or equal to 0")
        if self.db_pool_timeout_seconds <= 0:
            raise ValueError("DB_POOL_TIMEOUT_SECONDS must be greater than 0")
        if self.db_pool_recycle_seconds < -1:
            raise ValueError("DB_POOL_RECYCLE_SECONDS must be greater than or equal to -1")
        if self.daily_sync_cron is None:
            if self.daily_sync_hour is not None or self.daily_sync_minute is not None:
                hour = self.daily_sync_hour if self.daily_sync_hour is not None else 0
                minute = self.daily_sync_minute if self.daily_sync_minute is not None else 0
                if not 0 <= hour <= 23:
                    raise ValueError("DAILY_SYNC_HOUR must be between 0 and 23")
                if not 0 <= minute <= 59:
                    raise ValueError("DAILY_SYNC_MINUTE must be between 0 and 59")
                self.daily_sync_cron = f"{minute} {hour} * * *"
            else:
                self.daily_sync_cron = "0 0 * * *"
        validate_cron_expression(self.daily_sync_cron)
        if self.comic_cover_storage_parent_folder_id.strip() == "":
            self.comic_cover_storage_parent_folder_id = "root"
        self.comic_cover_storage_folder_name = self.comic_cover_storage_folder_name.strip() or "__driver_comic_covers__"
        if self.comic_cover_max_width <= 0:
            raise ValueError("COMIC_COVER_MAX_WIDTH must be greater than 0")
        if self.comic_cover_max_height <= 0:
            raise ValueError("COMIC_COVER_MAX_HEIGHT must be greater than 0")
        if self.comic_cover_target_bytes <= 0:
            raise ValueError("COMIC_COVER_TARGET_BYTES must be greater than 0")
        _ = [int(part.strip()) for part in self.comic_cover_jpeg_quality_steps.split(",") if part.strip()]
        if not self.comic_rar_tools_dir:
            local_app_data = os.getenv("LOCALAPPDATA")
            if local_app_data:
                self.comic_rar_tools_dir = str(Path(local_app_data) / "OneDriveCBRManagement" / "tools")
            else:
                self.comic_rar_tools_dir = str(PROJECT_DIR / ".tools")
        self.comic_rar_tools_dir = os.path.expandvars(str(Path(self.comic_rar_tools_dir).expanduser()))
        if self.comic_rar_tool_path:
            self.comic_rar_tool_path = os.path.expandvars(str(Path(self.comic_rar_tool_path).expanduser()))
        if self.comic_rar_tool_download_url:
            self.comic_rar_tool_download_url = self.comic_rar_tool_download_url.strip()
        self.redis_queue_name = self.redis_queue_name.strip() or "driver:jobs"
        if self.worker_concurrency <= 0:
            raise ValueError("WORKER_CONCURRENCY must be greater than 0")
        if self.worker_job_timeout_seconds <= 0:
            raise ValueError("WORKER_JOB_TIMEOUT_SECONDS must be greater than 0")
        return self

    @property
    def microsoft_authority(self) -> str:
        """Get the Microsoft authority URL.

        Returns
        -------
        str
            The Microsoft identity platform authority URL.
        """
        return f"https://login.microsoftonline.com/{self.microsoft_tenant_id}"

    @property
    def microsoft_scopes(self) -> list[str]:
        """Get the required Microsoft Graph API scopes.

        Returns
        -------
        list[str]
            List of OAuth2 scopes for Microsoft Graph.
            Note: offline_access is automatically requested by MSAL.
        """
        return [
            "User.Read",
            "Files.Read",
            "Files.Read.All",
            "Files.ReadWrite",
            "Files.ReadWrite.All",
        ]

    @property
    def google_scopes(self) -> list[str]:
        """Get required Google OAuth scopes."""
        return [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/drive",
        ]


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns
    -------
    Settings
        Application settings instance.
    """
    return Settings()
