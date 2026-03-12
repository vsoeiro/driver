import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from backend.services.ai import langgraph_agent as agent
from backend.services.ai.tools import ToolDefinition


def _settings(**overrides):
    payload = {
        "ai_base_url_local": "http://127.0.0.1:11434",
        "ai_base_url_remote": "",
        "ai_provider_mode": "local",
        "ai_api_key_remote": None,
        "ai_timeout_seconds": 30,
        "ai_model_default": "llama3",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


async def _noop_handler(session, args):
    return {"ok": True}


class _FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=self._responses.pop(0))


def test_model_candidates_and_normalization_helpers(monkeypatch):
    openai_calls = []
    ollama_calls = []

    monkeypatch.setattr(
        agent,
        "ChatOpenAI",
        lambda **kwargs: openai_calls.append(kwargs) or SimpleNamespace(kind="openai", kwargs=kwargs),
    )
    monkeypatch.setattr(
        agent,
        "ChatOllama",
        lambda **kwargs: ollama_calls.append(kwargs) or SimpleNamespace(kind="ollama", kwargs=kwargs),
    )

    local_runner = agent.LangGraphAgentRunner(
        _settings(ai_base_url_local="http://localhost:11434/v1", ai_model_default="llama3.2")
    )
    local_models = local_runner._model_candidates()

    assert len(local_models) == 2
    assert openai_calls[0]["base_url"] == "http://localhost:11434/v1"
    assert openai_calls[0]["api_key"] == "ollama"
    assert ollama_calls[0]["base_url"] == "http://localhost:11434"
    assert local_runner._normalize_local_openai_base_url("") == "http://127.0.0.1:11434/v1"
    assert local_runner._normalize_ollama_base_url("http://localhost:11434/v1") == "http://localhost:11434"

    gemini_runner = agent.LangGraphAgentRunner(
        _settings(
            ai_provider_mode="openai_compatible",
            ai_base_url_remote="https://generativelanguage.googleapis.com/v1beta",
            ai_api_key_remote="secret",
            ai_model_default="models/gemini-pro-latest",
        )
    )
    gemini_models = gemini_runner._model_candidates()

    assert len(gemini_models) == 1
    assert openai_calls[-1]["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert openai_calls[-1]["model"] == "gemini-2.5-pro"
    assert gemini_runner._resolve_model_name_for_provider("gemini") == "gemini-2.5-pro"
    assert gemini_runner._is_gemini_base_url("https://generativelanguage.googleapis.com/v1beta") is True


@pytest.mark.asyncio
async def test_build_args_model_and_langchain_tools_wrap_results(monkeypatch):
    runner = agent.LangGraphAgentRunner(_settings())
    execute_mock = AsyncMock(return_value={"total": 3})
    monkeypatch.setattr(agent, "execute_tool", execute_mock)

    read_definition = ToolDefinition(
        name="items.count",
        permission="read",
        description="Count items",
        input_schema={
            "properties": {
                "q": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["q"],
        },
        handler=_noop_handler,
    )
    write_definition = ToolDefinition(
        name="jobs.create",
        permission="write",
        description="Create a job",
        input_schema={"properties": {"account_id": {"type": "string"}}},
        handler=_noop_handler,
    )

    args_model = runner._build_args_model_for_tool(read_definition)
    validated = args_model(q="Saga", limit=5)
    assert validated.q == "Saga"
    assert validated.limit == 5

    wrapped_tools = runner._build_langchain_tools(
        session=object(),
        tool_registry={
            read_definition.name: read_definition,
            write_definition.name: write_definition,
        },
    )
    tool_map = {tool.name: tool for tool in wrapped_tools}

    read_payload = json.loads(await tool_map["items_count"].ainvoke({"q": "Saga", "limit": 5}))
    assert read_payload["status"] == "success"
    assert read_payload["arguments"] == {"q": "Saga", "limit": 5}
    assert read_payload["result"] == {"total": 3}

    write_payload = json.loads(await tool_map["jobs_create"].ainvoke({"account_id": "acc-1"}))
    assert write_payload["status"] == "pending_confirmation"
    assert write_payload["requires_confirmation"] is True

    execute_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(agent, "execute_tool", execute_mock)
    error_tools = runner._build_langchain_tools(
        session=object(),
        tool_registry={read_definition.name: read_definition},
    )
    error_payload = json.loads(await error_tools[0].ainvoke({"q": "Saga"}))
    assert error_payload["status"] == "failed"
    assert error_payload["error"] == "boom"


def test_parse_result_and_json_helpers():
    runner = agent.LangGraphAgentRunner(_settings())

    assert runner._parse_tool_message_content({"tool_name": "items.count"}) == {"tool_name": "items.count"}
    assert runner._parse_tool_message_content(['{"tool_name":"items.count","status":"success"}']) == {
        "tool_name": "items.count",
        "status": "success",
    }
    assert runner._extract_json_object('prefix {"tool_calls": []} suffix') == {"tool_calls": []}

    result = runner._parse_result(
        {
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "tool_name": "items.count",
                            "permission": "read",
                            "arguments": {"q": "Saga"},
                            "status": "success",
                            "duration_ms": 7,
                            "result": {"total": 2},
                        }
                    ),
                    tool_call_id="call-1",
                ),
                ToolMessage(content="not-json", tool_call_id="call-2"),
                AIMessage(content="Existem 2 arquivos."),
            ]
        },
        max_tool_calls=1,
    )

    assert result.assistant_message == "Existem 2 arquivos."
    assert len(result.traces) == 1
    assert result.traces[0].tool_name == "items.count"
    assert result.traces[0].result_summary == {"total": 2}

    fallback = runner._parse_result({"messages": "invalid"}, max_tool_calls=1)
    assert fallback.assistant_message == "Nao consegui processar a resposta do agente."


@pytest.mark.asyncio
async def test_run_gemini_without_native_tool_binding_collects_success_confirmation_and_unknown(monkeypatch):
    runner = agent.LangGraphAgentRunner(_settings(ai_provider_mode="gemini"))
    model = _FakeModel(
        [
            json.dumps(
                {
                    "assistant_message": "rascunho",
                    "tool_calls": [
                        {"tool_name": "items.count", "arguments": {"q": "Saga"}},
                        {"tool_name": "jobs.create", "arguments": {"account_id": "acc-1"}},
                        {"tool_name": "missing.tool", "arguments": {}},
                    ],
                },
                ensure_ascii=False,
            ),
            "Existem 3 itens.",
        ]
    )
    monkeypatch.setattr(runner, "_model_candidates", lambda: [model])
    execute_mock = AsyncMock(return_value={"total": 3})
    monkeypatch.setattr(agent, "execute_tool", execute_mock)

    tool_registry = {
        "items.count": ToolDefinition(
            name="items.count",
            permission="read",
            description="Count items",
            input_schema={"properties": {"q": {"type": "string"}}, "required": ["q"]},
            handler=_noop_handler,
        ),
        "jobs.create": ToolDefinition(
            name="jobs.create",
            permission="write",
            description="Create a job",
            input_schema={"properties": {"account_id": {"type": "string"}}},
            handler=_noop_handler,
        ),
    }

    result = await runner._run_gemini_without_native_tool_binding(
        session=object(),
        user_message="Quantos itens existem?",
        conversation_context=[{"role": "assistant", "content": "Contexto anterior"}],
        tool_registry=tool_registry,
        max_tool_calls=3,
    )

    assert result.assistant_message == "Existem 3 itens."
    assert [trace.status for trace in result.traces] == [
        "success",
        "pending_confirmation",
        "failed",
    ]
    assert result.traces[1].requires_confirmation is True
    assert result.traces[2].error_summary == "Unknown tool"
    execute_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_falls_back_between_models_and_generates_title(monkeypatch):
    runner = agent.LangGraphAgentRunner(_settings())

    monkeypatch.setattr(runner, "_model_candidates", lambda: ["bad-model", "good-model"])
    monkeypatch.setattr(runner, "_build_langchain_tools", lambda session, tool_registry: [])

    async def _fake_graph(*, model, tool_list, messages, max_tool_calls):
        if model == "bad-model":
            raise RuntimeError("boom")
        return {"messages": [AIMessage(content="Tudo certo")]}

    monkeypatch.setattr(runner, "_run_tool_calling_graph", _fake_graph)

    result = await runner.run(
        session=object(),
        user_message="Oi",
        conversation_context=[{"role": "user", "content": "Anterior"}],
        tool_registry={},
        max_tool_calls=2,
    )
    assert result.assistant_message == "Tudo certo"

    title_model = _FakeModel(['"Titulo util"\nOutra linha'])
    monkeypatch.setattr(runner, "_model_candidates", lambda: [title_model])
    title = await runner.generate_session_title(
        first_user_message="contar arquivos",
        first_assistant_message="resumo",
    )
    assert title == "Titulo util"
