from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import get_settings
from backend.db.models import Base, Item, LinkedAccount, MetadataCategory, MetadataRule
from backend.services.ai.chat_service import AIChatService
from backend.services.ai.langgraph_agent import AgentRunResult, AgentToolTrace


@pytest.mark.asyncio
async def test_ai_chat_qna_count_by_name_flow(monkeypatch):
    monkeypatch.setenv("AI_MODULE_ENABLED", "true")
    get_settings.cache_clear()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            account = LinkedAccount(
                id=uuid4(),
                provider="microsoft",
                provider_account_id="provider-acc-1",
                email="tester@example.com",
                display_name="Tester",
                access_token_encrypted="enc",
                refresh_token_encrypted="enc",
                token_expires_at=now,
                is_active=True,
            )
            session.add(account)
            await session.flush()
            session.add_all(
                [
                    Item(
                        account_id=account.id,
                        item_id="item-a",
                        parent_id="root",
                        name="Dylan Dog 001.cbz",
                        path="/Comics/Dylan Dog 001.cbz",
                        item_type="file",
                        extension="cbz",
                        size=123,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account.id,
                        item_id="item-b",
                        parent_id="root",
                        name="Dylan Dog 002.cbz",
                        path="/Comics/Dylan Dog 002.cbz",
                        item_type="file",
                        extension="cbz",
                        size=234,
                        created_at=now,
                        modified_at=now,
                    ),
                ]
            )
            await session.commit()

            service = AIChatService(session)
            chat = await service.create_session(title="AI")

            async def _fake_run(**kwargs):
                return AgentRunResult(
                    assistant_message="Encontrei 2 item(ns) para a busca por nome: 'Dylan Dog'.",
                    traces=[
                        AgentToolTrace(
                            tool_name="items.count_by_name",
                            permission="read",
                            arguments={"q": "Dylan Dog"},
                            status="success",
                            duration_ms=10,
                            result_summary={"total": 2, "query": "Dylan Dog"},
                        )
                    ],
                )

            service.agent_runner.run = _fake_run
            response = await service.post_message(chat.id, message="Quantos arquivos tenho com nome Dylan Dog?")

            assert response.tool_trace
            assert response.tool_trace[0].tool_name == "items.count_by_name"
            assert response.tool_trace[0].status == "success"
            assert response.tool_trace[0].result_summary["total"] == 2
            assert response.pending_confirmation is None
    finally:
        await engine.dispose()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_ai_chat_write_confirmation_flow(monkeypatch):
    monkeypatch.setenv("AI_MODULE_ENABLED", "true")
    get_settings.cache_clear()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            account = LinkedAccount(
                id=uuid4(),
                provider="microsoft",
                provider_account_id="provider-acc-2",
                email="tester2@example.com",
                display_name="Tester 2",
                access_token_encrypted="enc",
                refresh_token_encrypted="enc",
                token_expires_at=now,
                is_active=True,
            )
            category = MetadataCategory(name="Docs", is_active=True)
            session.add_all([account, category])
            await session.commit()

            service = AIChatService(session)
            chat = await service.create_session(title="AI")

            async def _fake_run(**kwargs):
                return AgentRunResult(
                    assistant_message="Posso criar a regra.",
                    traces=[
                        AgentToolTrace(
                            tool_name="rules.create_from_structured_payload",
                            permission="write",
                            arguments={
                                "rule": {
                                    "name": "Regra Dylan",
                                    "description": "Auto",
                                    "account_id": str(account.id),
                                    "is_active": True,
                                    "priority": 10,
                                    "path_contains": "Dylan",
                                    "path_prefix": None,
                                    "target_category_id": str(category.id),
                                    "target_values": {},
                                    "apply_metadata": True,
                                    "apply_rename": False,
                                    "rename_template": None,
                                    "apply_move": False,
                                    "destination_account_id": None,
                                    "destination_folder_id": "root",
                                    "destination_path_template": None,
                                    "include_folders": False,
                                }
                            },
                            status="pending_confirmation",
                            duration_ms=10,
                            requires_confirmation=True,
                        )
                    ],
                )

            service.agent_runner.run = _fake_run

            first = await service.post_message(chat.id, message="Cria essa regra")
            assert first.pending_confirmation is not None
            assert first.pending_confirmation.tool_name == "rules.create_from_structured_payload"

            confirmed = await service.resolve_confirmation(
                session_id=chat.id,
                confirmation_id=first.pending_confirmation.id,
                approve=True,
            )
            assert confirmed.pending_confirmation is not None
            assert confirmed.pending_confirmation.status == "approved"

            rule_count = await session.scalar(select(func.count(MetadataRule.id)))
            assert rule_count == 1
    finally:
        await engine.dispose()
        get_settings.cache_clear()
