from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.services.ai import llm_provider
from backend.services.ai.llm_provider import (
    HybridPlanner,
    LLMEndpoint,
    OpenAICompatibleProvider,
    _extract_json_object,
    _is_small_talk,
    heuristic_answer,
    heuristic_plan,
)


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(status_code: int, payload: dict):
    request = httpx.Request("POST", "https://llm.example/chat/completions")
    return httpx.Response(status_code, request=request, json=payload)


@pytest.mark.asyncio
async def test_openai_compatible_provider_generates_structured_plan_and_retries_without_response_format(monkeypatch):
    endpoint = LLMEndpoint(base_url="https://llm.example", api_key="secret", model="gpt-test", timeout_seconds=30)
    provider = OpenAICompatibleProvider(endpoint)
    client = _FakeAsyncClient([
        _response(400, {"error": "unsupported"}),
        _response(200, {"choices": [{"message": {"content": '{"intent":"jobs_overview","tool_calls":[{"tool_name":"jobs.status_overview","arguments":{"limit":25}}]}'}}]}),
    ])
    monkeypatch.setattr(llm_provider.httpx, "AsyncClient", lambda **_kwargs: client)

    plan = await provider.generate_structured_plan(
        user_message="Como estao os jobs?",
        conversation_context=[{"role": "assistant", "content": "Oi"}],
        tools_catalog=[{"name": "jobs.status_overview", "permission": "read", "description": "Resumo"}],
    )

    assert plan.intent == "jobs_overview"
    assert plan.tool_calls[0].tool_name == "jobs.status_overview"
    assert "Authorization" in client.calls[0]["headers"]
    assert "response_format" in client.calls[0]["json"]
    assert "response_format" not in client.calls[1]["json"]


@pytest.mark.asyncio
async def test_openai_compatible_provider_generates_answer():
    endpoint = LLMEndpoint(base_url="https://llm.example", api_key=None, model="gpt-test", timeout_seconds=30)
    provider = OpenAICompatibleProvider(endpoint)
    client = _FakeAsyncClient([
        _response(200, {"choices": [{"message": {"content": "Resposta final"}}]}),
    ])
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(llm_provider.httpx, "AsyncClient", lambda **_kwargs: client)

    try:
        answer = await provider.generate_answer(
            user_message="Quantos arquivos existem?",
            tool_summaries=[{"tool_name": "items.count_by_name", "result": {"total": 4}}],
        )
    finally:
        monkeypatch.undo()

    assert answer == "Resposta final"
    assert "Pergunta" in client.calls[0]["json"]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_hybrid_planner_falls_back_across_providers_and_then_to_heuristics():
    failing_provider = SimpleNamespace(
        generate_structured_plan=AsyncMock(side_effect=httpx.HTTPError("boom")),
        generate_answer=AsyncMock(side_effect=httpx.HTTPError("boom")),
    )
    succeeding_provider = SimpleNamespace(
        generate_structured_plan=AsyncMock(return_value=heuristic_plan("jobs")),
        generate_answer=AsyncMock(return_value="Resposta do provider"),
    )
    hybrid = HybridPlanner(providers=[failing_provider, succeeding_provider])

    plan = await hybrid.plan(
        user_message="jobs",
        conversation_context=[],
        tools_catalog=[],
    )
    answer = await hybrid.answer(user_message="jobs", tool_summaries=[{"tool_name": "jobs.status_overview"}])

    assert plan.intent == "jobs_overview"
    assert answer == "Resposta do provider"

    all_fail = HybridPlanner(
        providers=[
            SimpleNamespace(
                generate_structured_plan=AsyncMock(side_effect=httpx.HTTPError("boom")),
                generate_answer=AsyncMock(side_effect=httpx.HTTPError("boom")),
            )
        ]
    )
    fallback_plan = await all_fail.plan(user_message="mostrar duplicados", conversation_context=[], tools_catalog=[])
    fallback_answer = await all_fail.answer(user_message="oi", tool_summaries=[])
    assert fallback_plan.intent == "similar_items_report"
    assert "Nao encontrei dados suficientes" in fallback_answer


def test_heuristic_plan_covers_main_intents():
    assert heuristic_plan("mostrar duplicados").intent == "similar_items_report"
    assert heuristic_plan("top extensoes").intent == "top_extensions"
    assert heuristic_plan("como estao os jobs").intent == "jobs_overview"
    assert heuristic_plan("listar conta conectada").intent == "accounts_list"
    count_plan = heuristic_plan("quantos arquivos com nome Dylan Dog?")
    assert count_plan.intent == "count_by_name"
    assert count_plan.tool_calls[0].arguments["q"] == "Dylan Dog"
    assert heuristic_plan("preciso de ajuda").intent == "generic_qna"


def test_heuristic_answer_covers_multiple_tool_shapes():
    assert "4 item" in heuristic_answer(
        user_message="x",
        tool_summaries=[{"tool_name": "items.count_by_name", "arguments": {"q": "Dylan"}, "result": {"total": 4}}],
    )
    assert "Top extensoes" in heuristic_answer(
        user_message="x",
        tool_summaries=[{"tool_name": "items.top_extensions", "result": {"items": [{"extension": ".cbz", "count": 7}]}}],
    )
    assert "Resumo de jobs" in heuristic_answer(
        user_message="x",
        tool_summaries=[{"tool_name": "jobs.status_overview", "result": {"by_status": {"RUNNING": 2}}}],
    )
    assert "conta(s) conectada(s)" in heuristic_answer(
        user_message="x",
        tool_summaries=[{"tool_name": "accounts.list", "result": {"accounts": [{"email": "reader@example.com"}]}}],
    )
    assert heuristic_answer(user_message="x", tool_summaries=[{"tool_name": "unknown"}]) == "Consulta executada com sucesso."


def test_extract_json_object_and_small_talk_detection():
    assert _extract_json_object('{"intent":"ok"}') == {"intent": "ok"}
    assert _extract_json_object("prefix {\"intent\":\"ok\"} suffix") == {"intent": "ok"}
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("sem json")

    assert _is_small_talk("oi") is True
    assert _is_small_talk("tudo bem por ai") is True
    assert _is_small_talk("mostrar arquivos") is False
