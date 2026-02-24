"""Shared HTTP client helpers for OAuth-backed provider clients."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx

from backend.db.models import LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.provider_request_usage import provider_request_usage_tracker

TimeoutErrorFactory = Callable[[Exception], Exception]
ConnectionErrorFactory = Callable[[Exception], Exception]


class OAuthHTTPClientBase:
    """Reusable HTTP/OAuth behavior for provider-specific clients."""

    _shared_client: httpx.AsyncClient | None = None
    _shared_client_lock: asyncio.Lock | None = None

    def __init__(self, token_manager: TokenManager) -> None:
        self._token_manager = token_manager

    @classmethod
    async def _get_http_client(cls, *, timeout: httpx.Timeout) -> httpx.AsyncClient:
        if cls._shared_client is not None:
            return cls._shared_client
        if cls._shared_client_lock is None:
            cls._shared_client_lock = asyncio.Lock()
        async with cls._shared_client_lock:
            if cls._shared_client is None:
                cls._shared_client = httpx.AsyncClient(timeout=timeout)
        return cls._shared_client

    @classmethod
    async def close_http_client(cls) -> None:
        if cls._shared_client is None:
            return
        if cls._shared_client_lock is None:
            cls._shared_client_lock = asyncio.Lock()
        async with cls._shared_client_lock:
            if cls._shared_client is not None:
                await cls._shared_client.aclose()
                cls._shared_client = None

    async def _perform_oauth_request(
        self,
        *,
        method: str,
        url: str,
        account: LinkedAccount,
        timeout: httpx.Timeout,
        timeout_error_factory: TimeoutErrorFactory,
        connection_error_factory: ConnectionErrorFactory,
        request_headers: dict[str, str] | None = None,
        unauthorized_retry_log: Callable[[LinkedAccount], None] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(request_headers or {})

        async def _send(access_token: str) -> httpx.Response:
            client = await self._get_http_client(timeout=timeout)
            auth_headers = dict(headers)
            auth_headers["Authorization"] = f"Bearer {access_token}"
            response = await client.request(
                method=method,
                url=url,
                headers=auth_headers,
                timeout=timeout,
                **kwargs,
            )
            await provider_request_usage_tracker.record_response(
                provider=account.provider,
                status_code=response.status_code,
            )
            return response

        try:
            access_token = await self._token_manager.get_valid_access_token(account)
            response = await _send(access_token)
            if response.status_code == 401:
                if unauthorized_retry_log is not None:
                    unauthorized_retry_log(account)
                access_token = await self._token_manager.force_refresh_access_token(
                    account
                )
                response = await _send(access_token)
            return response
        except httpx.TimeoutException as exc:
            await provider_request_usage_tracker.record_transport_error(
                provider=account.provider,
                kind="timeout",
            )
            raise timeout_error_factory(exc) from exc
        except httpx.HTTPError as exc:
            await provider_request_usage_tracker.record_transport_error(
                provider=account.provider,
                kind="connection",
            )
            raise connection_error_factory(exc) from exc

    @staticmethod
    def parse_error_message(
        response: httpx.Response, *, default: str = "Request failed"
    ) -> str:
        """Best-effort parser for structured API errors."""
        try:
            data = response.json()
        except Exception:
            return response.text or default

        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message
            message = data.get("message")
            if isinstance(message, str) and message.strip():
                return message
        return response.text or default
