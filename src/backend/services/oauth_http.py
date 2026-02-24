"""Async OAuth HTTP helpers with retry/backoff policy."""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)


async def post_form_with_retry(
    *,
    url: str,
    payload: dict,
    timeout: httpx.Timeout,
    provider: str,
    max_attempts: int = 3,
) -> httpx.Response | None:
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
                details = exc.response.text if exc.response is not None else ""
                retryable = status_code is not None and status_code >= 500 and attempt < max_attempts
                logger.error(
                    "%s OAuth token request failed with status=%s attempt=%s/%s details=%s",
                    provider,
                    status_code,
                    attempt,
                    max_attempts,
                    details,
                )
                if not retryable:
                    return None
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "%s OAuth transport error attempt=%s/%s: %s",
                    provider,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt >= max_attempts:
                    return None

            sleep_for = delay_seconds + random.uniform(0.0, delay_seconds * 0.2)
            await asyncio.sleep(sleep_for)
            delay_seconds = min(3.0, delay_seconds * 2)

    return None
