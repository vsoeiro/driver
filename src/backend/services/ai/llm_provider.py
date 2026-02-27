from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class PlannedToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class PlannerResult(BaseModel):
    intent: str = "generic_qna"
    assistant_message: str | None = None
    tool_calls: list[PlannedToolCall] = Field(default_factory=list)


@dataclass(slots=True)
class LLMEndpoint:
    base_url: str
    api_key: str | None
    model: str
    timeout_seconds: int


class OpenAICompatibleProvider:
    def __init__(self, endpoint: LLMEndpoint) -> None:
        self._endpoint = endpoint

    async def generate_structured_plan(
        self,
        *,
        user_message: str,
        conversation_context: list[dict[str, str]],
        tools_catalog: list[dict[str, Any]],
    ) -> PlannerResult:
        url = self._endpoint.base_url.rstrip("/") + "/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._endpoint.api_key:
            headers["Authorization"] = f"Bearer {self._endpoint.api_key}"

        tool_lines = [
            f"- {tool['name']} ({tool['permission']}): {tool['description']}"
            for tool in tools_catalog
        ]
        system_prompt = (
            "You are a planner for an internal cloud operations assistant. "
            "Output JSON only with keys: intent, assistant_message, tool_calls. "
            "tool_calls must be a list of {tool_name, arguments}. "
            "Only use tools listed below. Never invent tools. "
            "If no tool is needed, return an empty list.\n"
            "Available tools:\n"
            + "\n".join(tool_lines)
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_context[-12:])
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self._endpoint.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        timeout = httpx.Timeout(float(self._endpoint.timeout_seconds), connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError:
                # Some OpenAI-compatible servers (including older Ollama bridges)
                # do not support response_format. Retry without it.
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                response = await client.post(url, headers=headers, json=fallback_payload)
                response.raise_for_status()
                data = response.json()

        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "{}")
        )
        parsed = _extract_json_object(content)
        return PlannerResult.model_validate(parsed)

    async def generate_answer(
        self,
        *,
        user_message: str,
        tool_summaries: list[dict[str, Any]],
    ) -> str:
        url = self._endpoint.base_url.rstrip("/") + "/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._endpoint.api_key:
            headers["Authorization"] = f"Bearer {self._endpoint.api_key}"

        system_prompt = (
            "You are an internal assistant. Answer in concise Brazilian Portuguese. "
            "Use tool results as source of truth. If uncertain, say what is missing."
        )
        payload = {
            "model": self._endpoint.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Pergunta: {user_message}\n"
                        f"Resultados de tools (JSON): {json.dumps(tool_summaries, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.1,
        }
        timeout = httpx.Timeout(float(self._endpoint.timeout_seconds), connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )


class HybridPlanner:
    def __init__(
        self,
        *,
        providers: list[OpenAICompatibleProvider],
    ) -> None:
        self._providers = providers

    async def plan(
        self,
        *,
        user_message: str,
        conversation_context: list[dict[str, str]],
        tools_catalog: list[dict[str, Any]],
    ) -> PlannerResult:
        for provider in self._providers:
            try:
                return await provider.generate_structured_plan(
                    user_message=user_message,
                    conversation_context=conversation_context,
                    tools_catalog=tools_catalog,
                )
            except (httpx.HTTPError, ValidationError, json.JSONDecodeError) as exc:
                logger.warning("AI planner provider failed, trying next provider: %s", exc)
        return heuristic_plan(user_message)

    async def answer(
        self,
        *,
        user_message: str,
        tool_summaries: list[dict[str, Any]],
    ) -> str:
        for provider in self._providers:
            try:
                content = await provider.generate_answer(
                    user_message=user_message,
                    tool_summaries=tool_summaries,
                )
                if content:
                    return content
            except httpx.HTTPError as exc:
                logger.warning("AI answer provider failed, trying next provider: %s", exc)
        return heuristic_answer(user_message=user_message, tool_summaries=tool_summaries)


def heuristic_plan(user_message: str) -> PlannerResult:
    text = user_message.lower()
    if _is_small_talk(text):
        return PlannerResult(
            intent="small_talk",
            assistant_message="Oi! Tudo bem por aqui. Posso te ajudar com buscas, contagens, duplicados e diagnostico de jobs.",
            tool_calls=[],
        )
    if "duplic" in text or "similar" in text:
        return PlannerResult(
            intent="similar_items_report",
            tool_calls=[PlannedToolCall(tool_name="items.similar_report", arguments={})],
        )
    if "extens" in text:
        return PlannerResult(
            intent="top_extensions",
            tool_calls=[PlannedToolCall(tool_name="items.top_extensions", arguments={"limit": 10})],
        )
    if "job" in text or "fila" in text:
        return PlannerResult(
            intent="jobs_overview",
            tool_calls=[PlannedToolCall(tool_name="jobs.status_overview", arguments={"limit": 100})],
        )
    if "conta" in text or "account" in text:
        return PlannerResult(
            intent="accounts_list",
            tool_calls=[PlannedToolCall(tool_name="accounts.list", arguments={})],
        )
    if "quant" in text or "count" in text:
        query = user_message.strip()
        for marker in ["nome ", "name ", "de ", "with name "]:
            idx = text.find(marker)
            if idx >= 0:
                query = user_message[idx + len(marker):].strip(" ?'\"")
                break
        return PlannerResult(
            intent="count_by_name",
            tool_calls=[PlannedToolCall(tool_name="items.count_by_name", arguments={"q": query})],
        )
    return PlannerResult(
        intent="generic_qna",
        assistant_message=(
            "Posso executar consultas para voce. Exemplos: "
            "'quantos arquivos com nome Dylan Dog', "
            "'mostrar duplicados', "
            "'como estao os jobs'."
        ),
        tool_calls=[],
    )


def heuristic_answer(*, user_message: str, tool_summaries: list[dict[str, Any]]) -> str:
    if not tool_summaries:
        return "Nao encontrei dados suficientes para responder com seguranca."
    first = tool_summaries[0]
    if first.get("tool_name") == "items.count_by_name":
        total = first.get("result", {}).get("total")
        query = first.get("arguments", {}).get("q", "")
        return f"Encontrei {total} item(ns) para a busca por nome: '{query}'."
    if first.get("tool_name") == "items.search":
        result = first.get("result", {}) or {}
        total = int(result.get("total") or 0)
        items = result.get("items") or []
        if total <= 0:
            return "Nao encontrei itens para essa busca."
        preview_names = [str(item.get("name") or "") for item in items[:5] if item.get("name")]
        if not preview_names:
            return f"Encontrei {total} item(ns) para essa busca."
        return f"Encontrei {total} item(ns). Primeiros resultados: {', '.join(preview_names)}."
    if first.get("tool_name") == "items.top_extensions":
        ext_rows = (first.get("result", {}) or {}).get("items") or []
        if not ext_rows:
            return "Nao encontrei extensoes para mostrar."
        top = ", ".join(f"{row.get('extension')}: {row.get('count')}" for row in ext_rows[:5])
        return f"Top extensoes: {top}."
    if first.get("tool_name") == "jobs.status_overview":
        by_status = (first.get("result", {}) or {}).get("by_status") or {}
        if not by_status:
            return "Nao encontrei jobs para resumir."
        status_text = ", ".join(f"{k}: {v}" for k, v in by_status.items())
        return f"Resumo de jobs por status: {status_text}."
    if first.get("tool_name") == "accounts.list":
        accounts = (first.get("result", {}) or {}).get("accounts") or []
        if not accounts:
            return "Nao ha contas conectadas no momento."
        preview = ", ".join(str(account.get("email") or "") for account in accounts[:5])
        return f"Voce tem {len(accounts)} conta(s) conectada(s): {preview}."
    return "Consulta executada com sucesso."


def _extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Parsed JSON is not an object", text, 0)
    return parsed


def _is_small_talk(text: str) -> bool:
    compact = text.strip()
    if compact in {"oi", "ola", "olá", "e ai", "e aí", "bom dia", "boa tarde", "boa noite"}:
        return True
    if "tudo bem" in compact:
        return True
    if len(compact.split()) <= 4 and any(greet in compact for greet in ["oi", "ola", "olá", "hello", "hi"]):
        return True
    return False
