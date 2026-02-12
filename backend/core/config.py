"""Application configuration settings.

This module provides configuration management through Pydantic Settings,
loading values from environment variables and .env files.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv

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

    app_secret_key: str = Field(alias="SECRET_KEY")
    token_encryption_key: str = Field(alias="ENCRYPTION_KEY")

    database_url: str = Field(alias="DATABASE_URL")

    redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/microsoft/callback", alias="MS_REDIRECT_URI")

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        if self.database_url.startswith("sqlite:///") and "aiosqlite" not in self.database_url:
            self.database_url = self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
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


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns
    -------
    Settings
        Application settings instance.
    """
    return Settings()
