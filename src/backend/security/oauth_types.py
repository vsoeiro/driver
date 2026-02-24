"""Shared OAuth token result types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class TokenResult:
    """Normalized result from OAuth token acquisition/refresh."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    id_token_claims: dict


class AuthServiceProtocol(Protocol):
    """Contract for OAuth auth services used by TokenManager."""

    async def refresh_access_token(self, refresh_token: str) -> TokenResult | None: ...
