from __future__ import annotations

import json

import httpx
import pytest

from backend.services.ai import AIInferenceConfig, OllamaClient


class _FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "http://localhost"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._data


class _FakeAsyncClient:
    response_get = _FakeResponse(200, {"models": []})
    response_post = _FakeResponse(200, {"response": "{}"})

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        return self.response_get

    async def post(self, url: str, json: dict):
        return self.response_post


@pytest.fixture
def client_config() -> AIInferenceConfig:
    return AIInferenceConfig(
        provider="ollama",
        base_url="http://localhost:11434",
        model="llama3.1:8b",
        temperature=0.1,
        timeout_seconds=30,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_ollama_health_success(monkeypatch, client_config):
    monkeypatch.setattr("backend.services.ai.httpx.AsyncClient", _FakeAsyncClient)
    client = OllamaClient(client_config)

    available, detail = await client.health()

    assert available is True
    assert detail == "Ollama reachable"


@pytest.mark.asyncio
async def test_ollama_generate_json_success(monkeypatch, client_config):
    _FakeAsyncClient.response_post = _FakeResponse(
        200,
        {"response": json.dumps({"category_name": "Invoice", "attributes": []})},
    )
    monkeypatch.setattr("backend.services.ai.httpx.AsyncClient", _FakeAsyncClient)
    client = OllamaClient(client_config)

    data = await client.generate_json(prompt="p", system="s")

    assert data["category_name"] == "Invoice"


@pytest.mark.asyncio
async def test_ollama_generate_json_invalid_payload(monkeypatch, client_config):
    _FakeAsyncClient.response_post = _FakeResponse(200, {"response": "not-json"})
    monkeypatch.setattr("backend.services.ai.httpx.AsyncClient", _FakeAsyncClient)
    client = OllamaClient(client_config)

    with pytest.raises(ValueError):
        await client.generate_json(prompt="p", system="s")

