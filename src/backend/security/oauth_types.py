"""Shared OAuth token result types."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TokenResult:
    """Normalized result from OAuth token acquisition/refresh."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    id_token_claims: dict
