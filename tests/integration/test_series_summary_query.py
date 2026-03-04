from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.application.metadata.series_query_service import SeriesQueryService
from backend.db.models import Base, Item, ItemMetadata, LinkedAccount, MetadataAttribute, MetadataCategory


@pytest.mark.asyncio
async def test_series_summary_query_aggregates_by_series():
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
                provider_account_id="provider-account-1",
                email="user@example.com",
                display_name="User",
                access_token_encrypted="enc",
                refresh_token_encrypted="enc",
                token_expires_at=now,
                is_active=True,
            )
            category = MetadataCategory(name="Series Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            attrs: dict[str, MetadataAttribute] = {}
            for key, name in [
                ("series", "Series"),
                ("volume", "Volume"),
                ("issue_number", "Issue Number"),
                ("max_volumes", "Max Volumes"),
                ("max_issues", "Max Issues"),
                ("series_status", "Series Status"),
            ]:
                attr = MetadataAttribute(
                    category_id=category.id,
                    name=name,
                    data_type="text",
                    plugin_field_key=key,
                )
                attrs[key] = attr
                session.add(attr)
            await session.flush()

            for idx, item_name in enumerate(("OnePiece-1.cbz", "OnePiece-2.cbz", "DragonBall-1.cbz"), start=1):
                session.add(
                    Item(
                        account_id=account.id,
                        item_id=f"item-{idx}",
                        parent_id="root",
                        name=item_name,
                        path=f"/Comics/{item_name}",
                        item_type="file",
                        extension="cbz",
                        size=100 * idx,
                        created_at=now,
                        modified_at=now,
                    )
                )
            await session.flush()

            session.add_all(
                [
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-1",
                        category_id=category.id,
                        values={
                            str(attrs["series"].id): "One Piece",
                            str(attrs["volume"].id): "1",
                            str(attrs["issue_number"].id): "1",
                            str(attrs["max_volumes"].id): "2",
                            str(attrs["max_issues"].id): "10",
                            str(attrs["series_status"].id): "ongoing",
                        },
                    ),
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-2",
                        category_id=category.id,
                        values={
                            str(attrs["series"].id): "One Piece",
                            str(attrs["volume"].id): "1",
                            str(attrs["issue_number"].id): "2",
                            str(attrs["series_status"].id): "ongoing",
                        },
                    ),
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-3",
                        category_id=category.id,
                        values={
                            str(attrs["series"].id): "Dragon Ball",
                            str(attrs["volume"].id): "3",
                            str(attrs["issue_number"].id): "1",
                            str(attrs["max_volumes"].id): "3",
                            str(attrs["series_status"].id): "completed",
                        },
                    ),
                ]
            )
            await session.commit()

            service = SeriesQueryService(session)
            summary = await service.get_category_series_summary(
                category_id=category.id,
                page=1,
                page_size=10,
                sort_by="series",
                sort_order="asc",
                q=None,
                search_fields="both",
                account_id=account.id,
                item_type="file",
                metadata_filters=None,
            )

            assert summary.total == 2
            assert len(summary.rows) == 2

            one_piece = next(row for row in summary.rows if row.series_name == "One Piece")
            assert one_piece.total_items == 2
            assert one_piece.owned_volumes == [1]
            assert one_piece.owned_issues_count == 2
            assert one_piece.issues_by_volume == {"1": [1, 2]}
            assert one_piece.max_volumes == 2
            assert one_piece.series_status == "ongoing"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_series_summary_query_counts_issues_without_volume():
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
                provider_account_id="provider-account-2",
                email="user2@example.com",
                display_name="User 2",
                access_token_encrypted="enc",
                refresh_token_encrypted="enc",
                token_expires_at=now,
                is_active=True,
            )
            category = MetadataCategory(name="Series Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            attrs: dict[str, MetadataAttribute] = {}
            for key, name in [
                ("series", "Series"),
                ("issue_number", "Issue Number"),
            ]:
                attr = MetadataAttribute(
                    category_id=category.id,
                    name=name,
                    data_type="text",
                    plugin_field_key=key,
                )
                attrs[key] = attr
                session.add(attr)
            await session.flush()

            for idx, item_name in enumerate(("Batman-1.cbz", "Batman-2.cbz"), start=1):
                session.add(
                    Item(
                        account_id=account.id,
                        item_id=f"item-bat-{idx}",
                        parent_id="root",
                        name=item_name,
                        path=f"/Comics/{item_name}",
                        item_type="file",
                        extension="cbz",
                        size=100 * idx,
                        created_at=now,
                        modified_at=now,
                    )
                )
            await session.flush()

            session.add_all(
                [
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-bat-1",
                        category_id=category.id,
                        values={
                            str(attrs["series"].id): "Batman",
                            str(attrs["issue_number"].id): "1",
                        },
                    ),
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-bat-2",
                        category_id=category.id,
                        values={
                            str(attrs["series"].id): "Batman",
                            str(attrs["issue_number"].id): "2",
                        },
                    ),
                ]
            )
            await session.commit()

            service = SeriesQueryService(session)
            summary = await service.get_category_series_summary(
                category_id=category.id,
                page=1,
                page_size=10,
                sort_by="series",
                sort_order="asc",
                q=None,
                search_fields="both",
                account_id=account.id,
                item_type="file",
                metadata_filters=None,
            )

            assert summary.total == 1
            assert len(summary.rows) == 1
            batman = summary.rows[0]
            assert batman.series_name == "Batman"
            assert batman.total_items == 2
            assert batman.owned_volumes == []
            assert batman.owned_issues_count == 2
            assert batman.issues_by_volume == {}
    finally:
        await engine.dispose()
