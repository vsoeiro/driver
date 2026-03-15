"""Async OAuth HTTP helpers with retry/backoff policy."""

from __future__ import annotations

import asyncio
import json
import logging
import random

import httpx

logger = logging.getLogger(__name__)


class OAuthTokenRequestError(Exception):
    """Raised when an OAuth token request fails."""

    def __init__(
        self,
        *,
        provider: str,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        details: str | None = None,
        transient: bool = False,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        self.transient = transient
        super().__init__(message)


def _extract_error_details(response: httpx.Response | None) -> tuple[str | None, str]:
    if response is None:
        return None, ""

    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        text = response.text.strip()
        return None, text

    if not isinstance(payload, dict):
        return None, response.text.strip()

    error_code = payload.get("error")
    detail_parts = []
    for field in ("error_description", "error_summary", "message"):
        value = payload.get(field)
        if value:
            detail_parts.append(str(value))

    if not detail_parts and error_code:
        detail_parts.append(str(error_code))

    details = " | ".join(detail_parts) if detail_parts else response.text.strip()
    return str(error_code) if error_code else None, details


async def post_form_with_retry(
    *,
    url: str,
    payload: dict,
    timeout: httpx.Timeout,
    provider: str,
    max_attempts: int = 3,
) -> httpx.Response:
    """POST form data with bounded retry + exponential backoff + jitter."""
    delay_seconds = 0.35
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                error_code, details = _extract_error_details(exc.response)
                retryable_status = status_code in {429} or (status_code is not None and status_code >= 500)
                retryable = retryable_status and attempt < max_attempts
                logger.error(
                    "%s OAuth token request failed with status=%s attempt=%s/%s error=%s details=%s",
                    provider,
                    status_code,
                    attempt,
                    max_attempts,
                    error_code,
                    details,
                )
                if not retryable:
                    raise OAuthTokenRequestError(
                        provider=provider,
                        message=f"{provider} OAuth token request failed",
                        status_code=status_code,
                        error_code=error_code,
                        details=details or None,
                        transient=retryable_status,
                    ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "%s OAuth transport error attempt=%s/%s: %s",
                    provider,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt >= max_attempts:
                    raise OAuthTokenRequestError(
                        provider=provider,
                        message=f"{provider} OAuth token request failed after transport retries",
                        details=str(exc),
                        transient=True,
                    ) from exc

            sleep_for = delay_seconds + random.uniform(0.0, delay_seconds * 0.2)
            await asyncio.sleep(sleep_for)
            delay_seconds = min(3.0, delay_seconds * 2)
    raise OAuthTokenRequestError(
        provider=provider,
        message=f"{provider} OAuth token request exhausted retries",
        transient=True,
    )
