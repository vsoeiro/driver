from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DriveOrganizerError
from backend.core.config import Settings
from backend.services.ai.redaction import redact_object
from backend.services.ai.tools import ToolDefinition, execute_tool

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentToolTrace:
    tool_name: str
    permission: str
    arguments: dict[str, Any]
    status: str
    duration_ms: int | None
    result_summary: dict[str, Any] | None = None
    error_summary: str | None = None
    requires_confirmation: bool = False


@dataclass(slots=True)
class AgentRunResult:
    assistant_message: str
    traces: list[AgentToolTrace]


class LangGraphAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _model_candidates(self) -> list[Any]:
        base_local = (self._settings.ai_base_url_local or "").strip()
        base_remote = (self._settings.ai_base_url_remote or "").strip()
        mode = (self._settings.ai_provider_mode or "local").strip().lower()
        remote_is_gemini = self._is_gemini_base_url(base_remote)

        candidates: list[tuple[str, str | None, str]] = []
        if mode == "local":
            if base_local:
                candidates.append((base_local, None, "local"))
        elif mode == "gemini":
            candidates.append(
                (
                    self._normalize_gemini_openai_base_url(base_remote),
                    self._settings.ai_api_key_remote,
                    "gemini",
                )
            )
        elif mode == "openai_compatible":
            if base_remote:
                provider_kind = "gemini" if remote_is_gemini else "openai_compatible"
                candidates.append((base_remote, self._settings.ai_api_key_remote, provider_kind))

        models: list[Any] = []
        for base_url, api_key, provider_kind in candidates:
            model_name = self._resolve_model_name_for_provider(provider_kind)
            if provider_kind == "local":
                local_openai_url = self._normalize_local_openai_base_url(base_url)
                models.append(
                    ChatOpenAI(
                        model=model_name,
                        base_url=local_openai_url,
                        api_key=api_key or "ollama",
                        timeout=float(self._settings.ai_timeout_seconds),
                        temperature=0,
                    )
                )
                models.append(
                    ChatOllama(
                        model=model_name,
                        base_url=self._normalize_ollama_base_url(base_url),
                        temperature=0,
                        timeout=float(self._settings.ai_timeout_seconds),
                    )
                )
            else:
                models.append(
                    ChatOpenAI(
                        model=model_name,
                        base_url=(
                            self._normalize_gemini_openai_base_url(base_url)
                            if provider_kind == "gemini"
                            else base_url
                        ),
                        api_key=api_key or "ollama",
                        timeout=float(self._settings.ai_timeout_seconds),
                        temperature=0,
                    )
                )
        return models

    def _resolve_model_name_for_provider(self, provider_kind: str) -> str:
        model_name = str(self._settings.ai_model_default or "").strip()
        if provider_kind != "gemini":
            return model_name

        # Gemini OpenAI-compatible endpoint expects "gemini-..." format,
        # not "models/gemini-..." used by native generateContent endpoint.
        if model_name.startswith("models/"):
            model_name = model_name.split("/", 1)[1].strip()
        if not model_name:
            return "gemini-2.0-flash"
        if model_name in {"gemini-flash-latest", "flash-latest"}:
            return "gemini-2.0-flash"
        if model_name in {"gemini-pro-latest", "pro-latest"}:
            return "gemini-2.5-pro"
        if model_name.startswith("gemini-"):
            return model_name
        return "gemini-2.0-flash"

    @staticmethod
    def _normalize_ollama_base_url(base_url: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if normalized.endswith("/v1"):
            normalized = normalized[:-3]
        return normalized or "http://127.0.0.1:11434"

    @staticmethod
    def _normalize_local_openai_base_url(base_url: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            normalized = "http://127.0.0.1:11434"
        if not normalized.endswith("/v1"):
            normalized = normalized + "/v1"
        return normalized

    @staticmethod
    def _normalize_gemini_openai_base_url(base_url: str | None) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        if normalized.endswith("/v1beta/openai"):
            return normalized
        if "generativelanguage.googleapis.com" in normalized:
            if normalized.endswith("/v1beta"):
                return normalized + "/openai"
            if normalized.endswith("/v1"):
                return normalized
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return normalized

    @staticmethod
    def _is_gemini_base_url(base_url: str | None) -> bool:
        normalized = (base_url or "").strip().lower()
        return "generativelanguage.googleapis.com" in normalized

    async def run(
        self,
        *,
        session: AsyncSession,
        user_message: str,
        conversation_context: list[dict[str, str]],
        tool_registry: dict[str, ToolDefinition],
        max_tool_calls: int,
    ) -> AgentRunResult:
        mode = (self._settings.ai_provider_mode or "local").strip().lower()
        base_remote = (self._settings.ai_base_url_remote or "").strip()
        use_gemini_manual_tools = mode == "gemini" or (
            mode == "openai_compatible" and self._is_gemini_base_url(base_remote)
        )
        if use_gemini_manual_tools:
            return await self._run_gemini_without_native_tool_binding(
                session=session,
                user_message=user_message,
                conversation_context=conversation_context,
                tool_registry=tool_registry,
                max_tool_calls=max_tool_calls,
            )
        tool_list = self._build_langchain_tools(session=session, tool_registry=tool_registry)

        messages = [
            SystemMessage(
                content=(
                    "Voce e um assistente interno de biblioteca de arquivos e operacoes. "
                    "Voce deve operar em modo TOOL-FIRST: para responder perguntas operacionais, chame as tools disponiveis e baseie a resposta nelas. "
                    "Use EXCLUSIVAMENTE as tools fornecidas para contagem, busca, duplicados, contas, jobs e quaisquer consultas de estado. "
                    "NUNCA chame tools para saudacao, despedida ou conversa casual curta. "
                    "Quando a pergunta pedir QUANTIDADE de arquivos por conta, sempre use items.count com account_id. "
                    "Se account_id estiver como alias textual (ex: 'google', 'microsoft'), primeiro use accounts.resolve quando necessario e depois items.count com UUID. "
                    "Se houver ambiguidade, peca ao usuario email/UUID da conta, sem inventar valores. "
                    "Para follow-ups como 'no total', 'na pasta X', 'na conta Y', chame novamente a tool adequada com filtros corretos. "
                    "Para perguntas sobre pasta, prefira items.count com path_contains (ou path_prefix quando realmente for prefixo). "
                    "Nao invente resultados e nao use endpoint externo. "
                    "Depois de usar tools, responda de forma objetiva, sem repetir regras internas. "
                    "Nunca inclua JSON de tool call na resposta final."
                    f"Nao execute mais de {max_tool_calls} tool calls por pergunta."
                )
            )
        ]
        for item in conversation_context[-12:]:
            role = str(item.get("role") or "")
            content = str(item.get("content") or "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=user_message))

        for model in self._model_candidates():
            try:
                result = await self._run_tool_calling_graph(
                    model=model,
                    tool_list=tool_list,
                    messages=messages,
                    max_tool_calls=max_tool_calls,
                )
                return self._parse_result(result, max_tool_calls=max_tool_calls)
            except Exception as exc:
                logger.warning("LangGraph agent execution failed, trying next model: %s", exc)
        raise DriveOrganizerError(
            "Falha ao executar agente LangGraph com os provedores configurados.",
            status_code=503,
        )

    async def _run_gemini_without_native_tool_binding(
        self,
        *,
        session: AsyncSession,
        user_message: str,
        conversation_context: list[dict[str, str]],
        tool_registry: dict[str, ToolDefinition],
        max_tool_calls: int,
    ) -> AgentRunResult:
        models = self._model_candidates()
        if not models:
            raise DriveOrganizerError("Nenhum provider Gemini configurado.", status_code=503)
        model = models[0]

        tools_catalog = [
            {
                "name": tool.name,
                "permission": tool.permission,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tool_registry.values()
        ]
        planner_messages: list[Any] = [
            SystemMessage(
                content=(
                    "Voce e um planejador de tools. "
                    "Retorne APENAS JSON com as chaves: assistant_message, tool_calls. "
                    "tool_calls deve ser lista de objetos {tool_name, arguments}. "
                    "Use somente os nomes de tools fornecidos. "
                    "Se nao precisar tool, retorne lista vazia."
                )
            ),
            SystemMessage(content=f"Tools disponiveis: {json.dumps(tools_catalog, ensure_ascii=False)}"),
        ]
        for item in conversation_context[-12:]:
            role = str(item.get("role") or "")
            content = str(item.get("content") or "")
            if role == "user":
                planner_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                planner_messages.append(AIMessage(content=content))
        planner_messages.append(HumanMessage(content=user_message))

        plan_response = await model.ainvoke(planner_messages)
        plan_text = str(getattr(plan_response, "content", "") or "").strip()
        plan_payload = self._extract_json_object(plan_text)
        planned_calls = plan_payload.get("tool_calls") if isinstance(plan_payload.get("tool_calls"), list) else []

        traces: list[AgentToolTrace] = []
        for call in planned_calls[:max_tool_calls]:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("tool_name") or "").strip()
            arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            definition = tool_registry.get(tool_name)
            if not definition:
                traces.append(
                    AgentToolTrace(
                        tool_name=tool_name or "unknown",
                        permission="read",
                        arguments=arguments,
                        status="failed",
                        duration_ms=0,
                        error_summary="Unknown tool",
                    )
                )
                continue

            started = perf_counter()
            if definition.permission != "read":
                traces.append(
                    AgentToolTrace(
                        tool_name=definition.name,
                        permission=definition.permission,
                        arguments=redact_object(arguments),
                        status="pending_confirmation",
                        duration_ms=int((perf_counter() - started) * 1000),
                        requires_confirmation=True,
                    )
                )
                continue

            try:
                result = await execute_tool(
                    session,
                    registry=tool_registry,
                    tool_name=definition.name,
                    arguments=arguments,
                )
                traces.append(
                    AgentToolTrace(
                        tool_name=definition.name,
                        permission=definition.permission,
                        arguments=redact_object(arguments),
                        status="success",
                        duration_ms=int((perf_counter() - started) * 1000),
                        result_summary=redact_object(result),
                    )
                )
            except Exception as exc:
                traces.append(
                    AgentToolTrace(
                        tool_name=definition.name,
                        permission=definition.permission,
                        arguments=redact_object(arguments),
                        status="failed",
                        duration_ms=int((perf_counter() - started) * 1000),
                        error_summary=str(exc),
                    )
                )

        answer_messages: list[Any] = [
            SystemMessage(
                content=(
                    "Responda de forma objetiva em Portugues-BR usando os resultados das tools como fonte de verdade. "
                    "Se faltar dado, diga claramente o que falta."
                )
            ),
            HumanMessage(
                content=(
                    f"Pergunta do usuario: {user_message}\n"
                    f"Traces de tools (JSON): {json.dumps([t.__dict__ for t in traces], ensure_ascii=False)}"
                )
            ),
        ]
        final_answer = str(plan_payload.get("assistant_message") or "").strip()
        try:
            answer_response = await model.ainvoke(answer_messages)
            model_answer = str(getattr(answer_response, "content", "") or "").strip()
            if model_answer:
                final_answer = model_answer
        except Exception:
            pass

        if not final_answer:
            final_answer = "Consulta concluida."
        return AgentRunResult(assistant_message=final_answer, traces=traces)

    async def generate_session_title(
        self,
        *,
        first_user_message: str,
        first_assistant_message: str,
    ) -> str | None:
        prompt = (
            "Gere um titulo curto (max 6 palavras) para esta sessao em Portugues-BR. "
            "Seja especifico ao tema principal. Retorne apenas o titulo sem aspas.\n"
            f"Usuario: {first_user_message}\n"
            f"Assistente: {first_assistant_message}"
        )
        for model in self._model_candidates():
            try:
                response = await model.ainvoke(
                    [
                        SystemMessage(content="Voce resume conversas em titulos curtos e claros."),
                        HumanMessage(content=prompt),
                    ]
                )
                text = str(getattr(response, "content", "") or "").strip()
                if not text:
                    continue
                line = text.splitlines()[0].strip().strip("\"' ")
                if not line:
                    continue
                return line[:80]
            except Exception as exc:
                logger.warning("Title generation failed, trying next model: %s", exc)
        return None

    async def _run_tool_calling_graph(
        self,
        *,
        model: Any,
        tool_list: list,
        messages: list[Any],
        max_tool_calls: int,
    ) -> dict[str, Any]:
        model_with_tools = model.bind_tools(tool_list)
        tool_node = ToolNode(tool_list)

        async def assistant_node(state: MessagesState) -> dict[str, list[Any]]:
            response = await model_with_tools.ainvoke(state["messages"])
            return {"messages": [response]}

        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("assistant", assistant_node)
        graph_builder.add_node("tools", tool_node)
        graph_builder.add_edge(START, "assistant")
        graph_builder.add_conditional_edges(
            "assistant",
            tools_condition,
            {
                "tools": "tools",
                "__end__": END,
            },
        )
        graph_builder.add_edge("tools", "assistant")
        graph = graph_builder.compile()
        return await graph.ainvoke(
            {"messages": messages},
            config={"recursion_limit": max(8, max_tool_calls * 4)},
        )

    def _build_langchain_tools(
        self,
        *,
        session: AsyncSession,
        tool_registry: dict[str, ToolDefinition],
    ) -> list:
        tools = []

        for definition in tool_registry.values():
            schema_text = json.dumps(definition.input_schema, ensure_ascii=False)
            args_model = self._build_args_model_for_tool(definition)

            async def _run(_definition: ToolDefinition = definition, **kwargs: Any) -> str:
                started = perf_counter()
                arguments = {}
                for key, value in kwargs.items():
                    if value is None:
                        continue
                    if isinstance(value, str) and not value.strip():
                        continue
                    if isinstance(value, (list, dict)) and not value:
                        continue
                    arguments[key] = value
                if _definition.permission != "read":
                    payload = {
                        "tool_name": _definition.name,
                        "permission": _definition.permission,
                        "arguments": redact_object(arguments),
                        "status": "pending_confirmation",
                        "requires_confirmation": True,
                        "duration_ms": int((perf_counter() - started) * 1000),
                    }
                    return json.dumps(payload, ensure_ascii=False)

                try:
                    result = await execute_tool(
                        session,
                        registry=tool_registry,
                        tool_name=_definition.name,
                        arguments=arguments,
                    )
                    payload = {
                        "tool_name": _definition.name,
                        "permission": _definition.permission,
                        "arguments": redact_object(arguments),
                        "status": "success",
                        "requires_confirmation": False,
                        "duration_ms": int((perf_counter() - started) * 1000),
                        "result": redact_object(result),
                    }
                except Exception as exc:
                    payload = {
                        "tool_name": _definition.name,
                        "permission": _definition.permission,
                        "arguments": redact_object(arguments),
                        "status": "failed",
                        "requires_confirmation": False,
                        "duration_ms": int((perf_counter() - started) * 1000),
                        "error": str(exc),
                    }
                return json.dumps(payload, ensure_ascii=False)

            tool_name = definition.name.replace(".", "_").replace("-", "_")
            tool_description = (
                f"{definition.description}. "
                f"Permission: {definition.permission}. "
                f"Input JSON schema: {schema_text}"
            )

            wrapped = tool(
                tool_name,
                args_schema=args_model,
                description=tool_description,
            )(_run)
            tools.append(wrapped)

        return tools

    @staticmethod
    def _build_args_model_for_tool(definition: ToolDefinition) -> type[BaseModel]:
        properties = (
            definition.input_schema.get("properties", {})
            if isinstance(definition.input_schema, dict)
            else {}
        )
        required = set(
            definition.input_schema.get("required", [])
            if isinstance(definition.input_schema, dict)
            else []
        )

        fields: dict[str, tuple[type[Any], Any]] = {}
        for key, spec in properties.items():
            json_type = spec.get("type") if isinstance(spec, dict) else None
            py_type: type[Any]
            if json_type == "integer":
                py_type = int
            elif json_type == "number":
                py_type = float
            elif json_type == "boolean":
                py_type = bool
            elif json_type == "array":
                py_type = list
            elif json_type == "object":
                py_type = dict
            else:
                py_type = str

            if key in required:
                fields[key] = (py_type, ...)
            else:
                fields[key] = (py_type | None, None)

        if not fields:
            fields = {"payload": (dict | None, None)}

        model_name = "Args_" + definition.name.replace(".", "_").replace("-", "_")
        return create_model(
            model_name,
            __config__=ConfigDict(extra="allow"),
            **fields,
        )

    def _parse_result(self, result: dict[str, Any], *, max_tool_calls: int) -> AgentRunResult:
        messages = result.get("messages") if isinstance(result, dict) else None
        if not isinstance(messages, list):
            return AgentRunResult(assistant_message="Nao consegui processar a resposta do agente.", traces=[])

        traces: list[AgentToolTrace] = []
        assistant_message = ""

        for message in messages:
            if isinstance(message, ToolMessage):
                parsed = self._parse_tool_message_content(message.content)
                if not parsed:
                    continue
                traces.append(
                    AgentToolTrace(
                        tool_name=str(parsed.get("tool_name") or "unknown"),
                        permission=str(parsed.get("permission") or "read"),
                        arguments=parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {},
                        status=str(parsed.get("status") or "success"),
                        duration_ms=int(parsed.get("duration_ms") or 0),
                        result_summary=parsed.get("result") if isinstance(parsed.get("result"), dict) else None,
                        error_summary=str(parsed.get("error")) if parsed.get("error") else None,
                        requires_confirmation=bool(parsed.get("requires_confirmation") or False),
                    )
                )
            elif isinstance(message, AIMessage):
                content = message.content
                if isinstance(content, str) and content.strip():
                    assistant_message = content.strip()

        if len(traces) > max_tool_calls:
            traces = traces[:max_tool_calls]

        if not assistant_message:
            assistant_message = "Consulta concluida."

        return AgentRunResult(assistant_message=assistant_message, traces=traces)

    @staticmethod
    def _parse_tool_message_content(content: Any) -> dict[str, Any] | None:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            content = "\n".join(str(part) for part in content)
        text = str(content or "").strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
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
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
