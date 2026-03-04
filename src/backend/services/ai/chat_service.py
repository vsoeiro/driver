from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.exceptions import DriveOrganizerError
from backend.db.models import AIChatMessage, AIChatSession, AIPendingConfirmation, AIToolCall
from backend.schemas.ai import (
    AIChatMessagePostResponse,
    AIChatMessageResponse,
    AIChatSessionResponse,
    AIConfirmationResponse,
    AIPendingConfirmationResponse,
    AIToolCatalogEntry,
    AIToolCatalogResponse,
    AIToolTraceItem,
)
from backend.services.ai.langgraph_agent import AgentToolTrace, LangGraphAgentRunner
from backend.services.ai.policy import PolicyEngine
from backend.services.ai.redaction import redact_object, redact_text
from backend.services.ai.tools import ToolDefinition, build_tool_registry, catalog_entries, execute_tool
from backend.services.app_settings import AppSettingsService


class AIChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.policy = PolicyEngine(
            max_tool_calls=self.settings.ai_max_tool_calls_per_message,
            max_rows_scanned=self.settings.ai_max_rows_scanned,
        )
        self.tool_registry = build_tool_registry()
        self.agent_runner = LangGraphAgentRunner(self.settings)

    def _ensure_enabled(self) -> None:
        if not self.settings.ai_module_enabled:
            raise DriveOrganizerError("AI module is disabled", status_code=404)

    async def create_session(self, *, title: str | None) -> AIChatSessionResponse:
        self._ensure_enabled()
        now = datetime.now(UTC)
        row = AIChatSession(
            title=(title or "New Session").strip()[:255] or "New Session",
            user_id="single_user",
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_session_response(row)

    async def list_sessions(self, *, limit: int, offset: int) -> list[AIChatSessionResponse]:
        self._ensure_enabled()
        safe_limit = min(100, max(1, int(limit)))
        safe_offset = max(0, int(offset))
        stmt = (
            select(AIChatSession)
            .order_by(desc(AIChatSession.updated_at), desc(AIChatSession.created_at))
            .limit(safe_limit)
            .offset(safe_offset)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_session_response(row) for row in rows]

    async def delete_session(self, session_id: UUID) -> None:
        self._ensure_enabled()
        row = await self._get_session_or_404(session_id)
        await self.session.delete(row)
        await self.session.commit()

    async def generate_session_title(self, session_id: UUID) -> AIChatSessionResponse:
        self._ensure_enabled()
        # Generate title inline to avoid dependency on worker availability.
        # Worker handler remains for backward compatibility/reprocessing flows.
        return await self.generate_session_title_now(session_id)

    async def generate_session_title_now(self, session_id: UUID) -> AIChatSessionResponse:
        self._ensure_enabled()
        await self._apply_runtime_ai_model_override()
        row = await self._get_session_or_404(session_id)
        if not self._is_default_session_title(row.title):
            return self._to_session_response(row)

        stmt = (
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at.asc())
        )
        messages = (await self.session.execute(stmt)).scalars().all()
        first_user = next((m for m in messages if m.role == "user"), None)
        first_assistant = next((m for m in messages if m.role == "assistant"), None)
        if not first_user or not first_assistant:
            return self._to_session_response(row)

        generated = await self.agent_runner.generate_session_title(
            first_user_message=first_user.content_redacted,
            first_assistant_message=first_assistant.content_redacted,
        )
        if generated:
            row.title = generated[:255]
            row.updated_at = datetime.now(UTC)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return self._to_session_response(row)

    async def get_messages(self, session_id: UUID, *, limit: int = 200) -> list[AIChatMessageResponse]:
        self._ensure_enabled()
        await self._get_session_or_404(session_id)
        stmt = (
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at.asc())
            .limit(min(1000, max(1, int(limit))))
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [AIChatMessageResponse.model_validate(row) for row in rows]

    async def tools_catalog(self) -> AIToolCatalogResponse:
        self._ensure_enabled()
        return AIToolCatalogResponse(
            tools=[AIToolCatalogEntry.model_validate(entry) for entry in catalog_entries(self.tool_registry)]
        )

    async def post_message(self, session_id: UUID, *, message: str) -> AIChatMessagePostResponse:
        self._ensure_enabled()
        await self._apply_runtime_ai_model_override()
        chat_session = await self._get_session_or_404(session_id)
        user_message = await self._persist_message(
            session_id=session_id,
            role="user",
            content=message,
        )

        history_context = await self._build_context_messages(session_id)
        run_result = await self.agent_runner.run(
            session=self.session,
            user_message=message,
            conversation_context=history_context,
            tool_registry=self.tool_registry,
            max_tool_calls=self.policy.limits.max_tool_calls,
        )

        self.policy.enforce_tool_budget(len(run_result.traces))

        first_write_trace = next(
            (trace for trace in run_result.traces if trace.requires_confirmation),
            None,
        )
        if first_write_trace is not None:
            pending = await self._create_pending_confirmation(
                session_id=session_id,
                tool_name=first_write_trace.tool_name,
                arguments=first_write_trace.arguments,
                impact_summary={
                    "assistant_message": run_result.assistant_message,
                },
            )
            assistant_text = (
                run_result.assistant_message
                or "Acao potencialmente mutavel detectada. Confirme para executar."
            )
            assistant_message = await self._persist_message(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
            )
            chat_session.updated_at = datetime.now(UTC)
            self.session.add(chat_session)
            await self.session.commit()
            return AIChatMessagePostResponse(
                assistant_message=AIChatMessageResponse.model_validate(assistant_message),
                tool_trace=[],
                pending_confirmation=AIPendingConfirmationResponse(
                    id=pending.id,
                    tool_name=pending.tool_name,
                    permission=pending.permission,
                    input_redacted=pending.input_redacted or {},
                    impact_summary=pending.impact_summary,
                    status=pending.status,
                    expires_at=pending.expires_at,
                ),
            )

        traces = []
        for trace in run_result.traces:
            persisted = await self._persist_agent_trace(
                session_id=session_id,
                message_id=user_message.id,
                trace=trace,
            )
            traces.append(persisted)
            await self._persist_tool_message_from_trace(session_id=session_id, trace=trace)
        traces = await self._maybe_chain_count_after_account_resolve(
            session_id=session_id,
            message_id=user_message.id,
            user_message=message,
            traces=traces,
        )

        assistant_text = run_result.assistant_message.strip() if run_result.assistant_message else ""
        assistant_text = self._sanitize_assistant_response(
            assistant_text=assistant_text,
            traces=traces,
            user_message=message,
        )
        assistant_text = self._enforce_count_grounding(
            assistant_text=assistant_text,
            traces=traces,
            user_message=message,
        )
        if not assistant_text:
            assistant_text = "Nao foi possivel gerar resposta util no momento."

        assistant_message = await self._persist_message(
            session_id=session_id,
            role="assistant",
            content=assistant_text,
        )
        chat_session.updated_at = datetime.now(UTC)
        self.session.add(chat_session)
        await self.session.commit()

        return AIChatMessagePostResponse(
            assistant_message=AIChatMessageResponse.model_validate(assistant_message),
            tool_trace=traces,
            pending_confirmation=None,
        )

    async def resolve_confirmation(
        self,
        *,
        session_id: UUID,
        confirmation_id: UUID,
        approve: bool,
    ) -> AIConfirmationResponse:
        self._ensure_enabled()
        chat_session = await self._get_session_or_404(session_id)
        row = await self.session.get(AIPendingConfirmation, confirmation_id)
        if not row or row.session_id != session_id:
            raise DriveOrganizerError("Pending confirmation not found", status_code=404)
        if row.status != "pending":
            raise DriveOrganizerError("Pending confirmation is already finalized", status_code=409)
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            row.status = "expired"
            self.session.add(row)
            await self.session.commit()
            raise DriveOrganizerError("Pending confirmation expired", status_code=409)

        if not approve:
            row.status = "rejected"
            row.updated_at = datetime.now(UTC)
            assistant_message = await self._persist_message(
                session_id=session_id,
                role="assistant",
                content="Acao rejeitada. Nenhuma alteracao foi aplicada.",
            )
            chat_session.updated_at = datetime.now(UTC)
            self.session.add_all([row, chat_session])
            await self.session.commit()
            return AIConfirmationResponse(
                assistant_message=AIChatMessageResponse.model_validate(assistant_message),
                tool_trace=[],
                pending_confirmation=AIPendingConfirmationResponse(
                    id=row.id,
                    tool_name=row.tool_name,
                    permission=row.permission,
                    input_redacted=row.input_redacted or {},
                    impact_summary=row.impact_summary,
                    status=row.status,
                    expires_at=row.expires_at,
                ),
            )

        action_payload = row.action_payload or {}
        tool_name = str(action_payload.get("tool_name") or row.tool_name)
        arguments = action_payload.get("arguments") if isinstance(action_payload.get("arguments"), dict) else {}
        definition = self.tool_registry.get(tool_name)
        if not definition:
            raise DriveOrganizerError("Unknown tool in pending confirmation", status_code=400)

        trace = await self._execute_and_persist_tool_call(
            session_id=session_id,
            message_id=None,
            definition=definition,
            arguments=arguments,
        )

        row.status = "approved"
        row.updated_at = datetime.now(UTC)
        self.session.add(row)

        result_text = json.dumps(trace.result_summary or {}, ensure_ascii=False)
        assistant_message = await self._persist_message(
            session_id=session_id,
            role="assistant",
            content=f"Acao confirmada e executada ({tool_name}). Resultado: {result_text}",
        )
        chat_session.updated_at = datetime.now(UTC)
        self.session.add(chat_session)
        await self.session.commit()

        return AIConfirmationResponse(
            assistant_message=AIChatMessageResponse.model_validate(assistant_message),
            tool_trace=[trace],
            pending_confirmation=AIPendingConfirmationResponse(
                id=row.id,
                tool_name=row.tool_name,
                permission=row.permission,
                input_redacted=row.input_redacted or {},
                impact_summary=row.impact_summary,
                status=row.status,
                expires_at=row.expires_at,
            ),
        )

    async def _get_session_or_404(self, session_id: UUID) -> AIChatSession:
        row = await self.session.get(AIChatSession, session_id)
        if not row:
            raise DriveOrganizerError("Chat session not found", status_code=404)
        return row

    @staticmethod
    def _is_default_session_title(title: str | None) -> bool:
        normalized = str(title or "").strip().lower()
        return normalized in {"new session", "new chat", ""}

    def _to_session_response(self, row: AIChatSession) -> AIChatSessionResponse:
        return AIChatSessionResponse(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            title_pending=self._is_default_session_title(row.title),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _persist_message(self, *, session_id: UUID, role: str, content: str) -> AIChatMessage:
        row = AIChatMessage(
            session_id=session_id,
            role=role,
            content_redacted=redact_text(content) if self.settings.ai_redaction_enabled else content,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def _build_context_messages(self, session_id: UUID) -> list[dict[str, str]]:
        stmt = (
            select(AIChatMessage)
            .where(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at.asc())
            .limit(12)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        context: list[dict[str, str]] = []
        for row in rows:
            if row.role not in {"user", "assistant"}:
                continue
            context.append({"role": row.role, "content": row.content_redacted})
        return context

    async def _create_pending_confirmation(
        self,
        *,
        session_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        impact_summary: dict[str, Any] | None,
    ) -> AIPendingConfirmation:
        row = AIPendingConfirmation(
            session_id=session_id,
            tool_name=tool_name,
            permission="write",
            input_redacted=redact_object(arguments),
            action_payload={"tool_name": tool_name, "arguments": arguments},
            impact_summary=redact_object(impact_summary or {}),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def _persist_agent_trace(
        self,
        *,
        session_id: UUID,
        message_id: UUID | None,
        trace: AgentToolTrace,
    ) -> AIToolTraceItem:
        row = AIToolCall(
            session_id=session_id,
            message_id=message_id,
            tool_name=trace.tool_name,
            permission=trace.permission,
            input_redacted=redact_object(trace.arguments),
            status=trace.status,
            duration_ms=trace.duration_ms,
            result_summary=redact_object(trace.result_summary) if trace.result_summary else None,
            error_summary=redact_text(trace.error_summary) if trace.error_summary else None,
        )
        self.session.add(row)
        await self.session.flush()
        return AIToolTraceItem(
            id=row.id,
            tool_name=row.tool_name,
            permission=row.permission,
            input_redacted=row.input_redacted or {},
            status=row.status,
            duration_ms=row.duration_ms,
            result_summary=row.result_summary,
            error_summary=row.error_summary,
            created_at=row.created_at,
        )

    @staticmethod
    def _sanitize_assistant_response(
        *,
        assistant_text: str,
        traces: list[AIToolTraceItem],
        user_message: str,
    ) -> str:
        text = str(assistant_text or "").strip()
        user_text = str(user_message or "").strip().lower()
        leaked_tool_json = (
            "\"tool_name\"" in text
            or "{\"tool_name\"" in text
            or "vou chamar a tool" in text.lower()
            or "```json" in text.lower()
            or "\"name\": \"items.count\"" in text
            or "\"name\":\"items.count\"" in text
        )
        if not leaked_tool_json:
            return text
        if not traces:
            return "Consulta concluida."

        last = traces[-1]
        result = last.result_summary or {}
        if last.status == "failed":
            if last.error_summary and "Conta ambigua" in last.error_summary:
                return (
                    "Encontrei mais de uma conta compativel. "
                    "Me diga o email/UUID da conta para eu contar os arquivos nela."
                )
            return f"Nao consegui concluir a consulta ({last.tool_name})."
        if last.tool_name == "items.count":
            total = int(result.get("total") or 0)
            return f"Encontrei {total} arquivo(s) com os filtros solicitados."
        if last.tool_name == "items.count_by_name":
            total = int(result.get("total") or 0)
            query = str(result.get("query") or "")
            return f"Encontrei {total} arquivo(s) para '{query}'."
        if last.tool_name == "accounts.list":
            accounts = result.get("accounts") if isinstance(result.get("accounts"), list) else []
            if "conta" in user_text or "arquivo" in user_text:
                microsoft_accounts = [a for a in accounts if str(a.get("provider") or "").lower() == "microsoft"]
                google_accounts = [a for a in accounts if str(a.get("provider") or "").lower() == "google"]
                if "microsoft" in user_text and len(microsoft_accounts) > 1:
                    emails = ", ".join(str(a.get("email") or "") for a in microsoft_accounts[:3])
                    return (
                        "Voce tem mais de uma conta Microsoft. "
                        f"Escolha uma pelo email para eu contar os arquivos: {emails}."
                    )
                if "google" in user_text and len(google_accounts) == 1:
                    return "Identifiquei a conta Google. Pode repetir a consulta para eu contar apenas nela."
            return f"Voce tem {len(accounts)} conta(s) conectada(s)."
        if last.tool_name == "accounts.resolve":
            accounts = result.get("accounts") if isinstance(result.get("accounts"), list) else []
            if len(accounts) == 0:
                return "Nao encontrei conta correspondente. Informe email ou UUID."
            if len(accounts) > 1:
                emails = ", ".join(str(a.get("email") or "") for a in accounts[:3])
                return (
                    "Encontrei mais de uma conta compativel. "
                    f"Informe email/UUID para continuar: {emails}."
                )
            return "Conta identificada. Vou usar essa conta na consulta."
        if last.tool_name == "items.search":
            total = int(result.get("total") or 0)
            return f"Encontrei {total} resultado(s)."
        return "Consulta concluida com sucesso."

    async def _persist_tool_message_from_trace(
        self,
        *,
        session_id: UUID,
        trace: AgentToolTrace,
    ) -> AIChatMessage:
        payload = {
            "tool_name": trace.tool_name,
            "permission": trace.permission,
            "status": trace.status,
            "duration_ms": trace.duration_ms,
            "arguments": redact_object(trace.arguments),
            "result_summary": redact_object(trace.result_summary) if trace.result_summary else None,
            "error_summary": redact_text(trace.error_summary) if trace.error_summary else None,
        }
        return await self._persist_message(
            session_id=session_id,
            role="tool",
            content=json.dumps(payload, ensure_ascii=False),
        )

    async def _execute_and_persist_tool_call(
        self,
        *,
        session_id: UUID,
        message_id: UUID | None,
        definition: ToolDefinition,
        arguments: dict[str, Any],
    ) -> AIToolTraceItem:
        start = perf_counter()
        status = "success"
        result_summary: dict[str, Any] | None = None
        error_summary: str | None = None

        try:
            result_summary = await execute_tool(
                self.session,
                registry=self.tool_registry,
                tool_name=definition.name,
                arguments=arguments,
            )
        except Exception as exc:
            status = "failed"
            error_summary = str(exc)
        duration_ms = int((perf_counter() - start) * 1000)

        row = AIToolCall(
            session_id=session_id,
            message_id=message_id,
            tool_name=definition.name,
            permission=definition.permission,
            input_redacted=redact_object(arguments),
            status=status,
            duration_ms=duration_ms,
            result_summary=redact_object(result_summary) if result_summary is not None else None,
            error_summary=redact_text(error_summary) if error_summary else None,
        )
        self.session.add(row)
        await self.session.flush()
        await self._persist_tool_message_from_trace(
            session_id=session_id,
            trace=AgentToolTrace(
                tool_name=definition.name,
                permission=definition.permission,
                arguments=arguments,
                status=status,
                duration_ms=duration_ms,
                result_summary=result_summary,
                error_summary=error_summary,
                requires_confirmation=False,
            ),
        )

        return AIToolTraceItem(
            id=row.id,
            tool_name=row.tool_name,
            permission=row.permission,
            input_redacted=row.input_redacted or {},
            status=row.status,
            duration_ms=row.duration_ms,
            result_summary=row.result_summary,
            error_summary=row.error_summary,
            created_at=row.created_at,
        )

    async def _apply_runtime_ai_model_override(self) -> None:
        runtime = await AppSettingsService(self.session).get_runtime_settings()
        model_name = str(runtime.ai_model_default or "").strip()
        if model_name and self.settings.ai_model_default != model_name:
            self.settings.ai_model_default = model_name
        provider_mode = str(runtime.ai_provider_mode or "").strip().lower()
        if provider_mode and self.settings.ai_provider_mode != provider_mode:
            self.settings.ai_provider_mode = provider_mode
        remote_url = str(runtime.ai_base_url_remote or "").strip()
        if (self.settings.ai_base_url_remote or "").strip() != remote_url:
            self.settings.ai_base_url_remote = remote_url or None
        remote_api_key = str(runtime.ai_api_key_remote or "").strip()
        if (self.settings.ai_api_key_remote or "").strip() != remote_api_key:
            self.settings.ai_api_key_remote = remote_api_key or None

    async def _maybe_chain_count_after_account_resolve(
        self,
        *,
        session_id: UUID,
        message_id: UUID,
        user_message: str,
        traces: list[AIToolTraceItem],
    ) -> list[AIToolTraceItem]:
        if not traces:
            return traces
        if any(trace.tool_name == "items.count" for trace in traces):
            return traces
        if not self._is_count_request(user_message):
            return traces

        last = traces[-1]
        if last.tool_name != "accounts.resolve" or last.status != "success":
            return traces
        result = last.result_summary or {}
        accounts = result.get("accounts") if isinstance(result.get("accounts"), list) else []
        if len(accounts) != 1:
            return traces
        account_id = accounts[0].get("id")
        if not account_id:
            return traces
        definition = self.tool_registry.get("items.count")
        if not definition:
            return traces

        chained_trace = await self._execute_and_persist_tool_call(
            session_id=session_id,
            message_id=message_id,
            definition=definition,
            arguments={"account_id": account_id, "item_type": "file"},
        )
        return [*traces, chained_trace]

    @staticmethod
    def _is_count_request(message: str) -> bool:
        text = re.sub(r"\s+", " ", str(message or "").strip().lower())
        return ("quant" in text or "qtd" in text or "total" in text) and (
            "arquivo" in text or "item" in text or "itens" in text
        )

    def _enforce_count_grounding(
        self,
        *,
        assistant_text: str,
        traces: list[AIToolTraceItem],
        user_message: str,
    ) -> str:
        user_text = re.sub(r"\s+", " ", str(user_message or "").strip().lower())
        if not self._is_count_request(user_message):
            # Follow-up curto do tipo "e conta microsoft?" deve permanecer ancorado
            # em tools de contagem/desambiguacao de conta.
            if not ("conta" in user_text and traces and traces[-1].tool_name == "accounts.resolve"):
                return assistant_text
        if not traces:
            return assistant_text
        successful_counts = [
            trace for trace in traces
            if trace.tool_name == "items.count" and trace.status == "success"
        ]
        if successful_counts:
            result = successful_counts[-1].result_summary or {}
            total = int(result.get("total") or 0)
            return f"Encontrei {total} arquivo(s) para esse filtro."

        successful_name_counts = [
            trace for trace in traces
            if trace.tool_name == "items.count_by_name" and trace.status == "success"
        ]
        if successful_name_counts:
            result = successful_name_counts[-1].result_summary or {}
            total = int(result.get("total") or 0)
            query = str(result.get("query") or "").strip()
            if query:
                return f"Encontrei {total} arquivo(s) com o nome contendo '{query}'."
            return f"Encontrei {total} arquivo(s) para esse filtro."

        last = traces[-1]
        if last.tool_name == "accounts.resolve" and last.status == "success":
            result = last.result_summary or {}
            accounts = result.get("accounts") if isinstance(result.get("accounts"), list) else []
            if len(accounts) > 1:
                emails = ", ".join(str(a.get("email") or "") for a in accounts[:3])
                return (
                    "Encontrei mais de uma conta compativel. "
                    f"Informe email/UUID para eu contar os arquivos: {emails}."
                )
            if len(accounts) == 0:
                return "Nao encontrei a conta informada. Envie email ou UUID."
        return "Nao consegui concluir a contagem com confianca."
