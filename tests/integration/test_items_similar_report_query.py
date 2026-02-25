from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.application.metadata.item_query_service import ItemQueryService
from backend.db.models import Base, Item, LinkedAccount


@pytest.mark.asyncio
async def test_similar_items_report_supports_same_and_cross_account_groups():
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
            account_a = LinkedAccount(
                id=uuid4(),
                provider="microsoft",
                provider_account_id="provider-account-a",
                email="a@example.com",
                display_name="Account A",
                access_token_encrypted="enc",
                refresh_token_encrypted="enc",
                token_expires_at=now,
                is_active=True,
            )
            account_b = LinkedAccount(
                id=uuid4(),
                provider="microsoft",
                provider_account_id="provider-account-b",
                email="b@example.com",
                display_name="Account B",
                access_token_encrypted="enc",
                refresh_token_encrypted="enc",
                token_expires_at=now,
                is_active=True,
            )
            session.add_all([account_a, account_b])
            await session.flush()

            session.add_all(
                [
                    Item(
                        account_id=account_a.id,
                        item_id="a-1",
                        parent_id="root",
                        name="Saga.cbz",
                        path="/Comics/Saga.cbz",
                        item_type="file",
                        extension="cbz",
                        size=200,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_a.id,
                        item_id="a-2",
                        parent_id="root",
                        name="Saga.cbz",
                        path="/Backup/Saga.cbz",
                        item_type="file",
                        extension="cbz",
                        size=200,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_b.id,
                        item_id="b-1",
                        parent_id="root",
                        name="Saga.cbz",
                        path="/Comics/Saga.cbz",
                        item_type="file",
                        extension="cbz",
                        size=200,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_a.id,
                        item_id="a-3",
                        parent_id="root",
                        name="Batman",
                        path="/Comics/Batman",
                        item_type="file",
                        extension=None,
                        size=300,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_b.id,
                        item_id="b-2",
                        parent_id="root",
                        name="Batman.cbz",
                        path="/Comics/Batman.cbz",
                        item_type="file",
                        extension="cbz",
                        size=300,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_b.id,
                        item_id="b-3",
                        parent_id="root",
                        name="venvfile.py",
                        path="/proj/.venv/lib/site-packages/venvfile.py",
                        item_type="file",
                        extension="py",
                        size=111,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_b.id,
                        item_id="b-4",
                        parent_id="root",
                        name="venvfile.py",
                        path="/proj/.venv/lib64/site-packages/venvfile.py",
                        item_type="file",
                        extension="py",
                        size=111,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_b.id,
                        item_id="b-5",
                        parent_id="root",
                        name="COVER.jpg",
                        path="/__covers__/COVER.jpg",
                        item_type="file",
                        extension="jpg",
                        size=222,
                        created_at=now,
                        modified_at=now,
                    ),
                    Item(
                        account_id=account_b.id,
                        item_id="b-6",
                        parent_id="root",
                        name="COVER.jpg",
                        path="/__covers__/COVER.jpg",
                        item_type="file",
                        extension="jpg",
                        size=222,
                        created_at=now,
                        modified_at=now,
                    ),
                ]
            )
            await session.commit()

            service = ItemQueryService(session)
            report = await service.get_similar_items_report(
                page=1,
                page_size=20,
                account_id=None,
                scope="all",
                sort_by="relevance",
                sort_order="desc",
                extensions=None,
                hide_low_priority=False,
            )

            assert report.total_groups == 3
            assert {group.match_type for group in report.groups} == {
                "with_extension",
                "without_extension",
            }
            assert report.collapsed_records == 1
            assert report.potential_savings_bytes > 0

            with_extension_group = next(group for group in report.groups if group.match_type == "with_extension")
            assert with_extension_group.name == "saga.cbz"
            assert with_extension_group.extension == "cbz"
            assert with_extension_group.total_items == 3
            assert with_extension_group.has_same_account_matches is True
            assert with_extension_group.has_cross_account_matches is True

            without_extension_group = next(group for group in report.groups if group.match_type == "without_extension")
            assert without_extension_group.name == "batman"
            assert without_extension_group.total_items == 2
            assert without_extension_group.has_same_account_matches is False
            assert without_extension_group.has_cross_account_matches is True
            assert without_extension_group.extensions == ["cbz"]

            account_filtered = await service.get_similar_items_report(
                page=1,
                page_size=20,
                account_id=account_a.id,
                scope="all",
                sort_by="relevance",
                sort_order="desc",
                extensions=None,
                hide_low_priority=False,
            )
            assert account_filtered.total_groups == 1
            assert account_filtered.groups[0].name == "saga.cbz"
            assert account_filtered.groups[0].total_accounts == 1

            same_scope = await service.get_similar_items_report(
                page=1,
                page_size=20,
                account_id=None,
                scope="same_account",
                sort_by="relevance",
                sort_order="desc",
                extensions=None,
                hide_low_priority=False,
            )
            assert same_scope.total_groups == 2
            assert all(group.has_same_account_matches for group in same_scope.groups)

            cross_scope = await service.get_similar_items_report(
                page=1,
                page_size=20,
                account_id=None,
                scope="cross_account",
                sort_by="relevance",
                sort_order="desc",
                extensions=None,
                hide_low_priority=False,
            )
            assert cross_scope.total_groups == 2

            by_name = await service.get_similar_items_report(
                page=1,
                page_size=20,
                account_id=None,
                scope="all",
                sort_by="name",
                sort_order="asc",
                extensions=None,
                hide_low_priority=False,
            )
            assert by_name.groups[0].name <= by_name.groups[-1].name

            only_cbz = await service.get_similar_items_report(
                page=1,
                page_size=20,
                account_id=None,
                scope="all",
                sort_by="relevance",
                sort_order="desc",
                extensions=["cbz"],
                hide_low_priority=False,
            )
            assert all("cbz" in (group.extensions or [group.extension]) for group in only_cbz.groups)

            low_priority_group = next(
                group for group in report.groups if group.name == "venvfile.py"
            )
            assert low_priority_group.priority_level == "low"
            assert ".venv" in low_priority_group.low_priority_reasons
    finally:
        await engine.dispose()
