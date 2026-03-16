from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.application.metadata.query_service import MetadataQueryService
from backend.db.models import Base, Item, ItemMetadata, LinkedAccount, MetadataAttribute, MetadataCategory


def _build_account(now: datetime) -> LinkedAccount:
    return LinkedAccount(
        id=uuid4(),
        provider="microsoft",
        provider_account_id=f"provider-{uuid4()}",
        email=f"user-{uuid4()}@example.com",
        display_name="User",
        access_token_encrypted="enc",
        refresh_token_encrypted="enc",
        token_expires_at=now,
        is_active=True,
    )


def _build_item(*, account_id, item_id: str, name: str, now: datetime) -> Item:
    return Item(
        account_id=account_id,
        item_id=item_id,
        parent_id="root",
        name=name,
        path=f"/Library/{name}",
        item_type="file",
        extension="cbz",
        size=1024,
        created_at=now,
        modified_at=now,
    )


@pytest.mark.asyncio
async def test_metadata_dashboard_query_aggregates_all_rows_and_expands_tags():
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
            account = _build_account(now)
            category = MetadataCategory(name="Dashboard Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            genre_attr = MetadataAttribute(category_id=category.id, name="Genre", data_type="text")
            read_attr = MetadataAttribute(category_id=category.id, name="Read", data_type="boolean")
            tags_attr = MetadataAttribute(category_id=category.id, name="Tags", data_type="tags")
            cover_attr = MetadataAttribute(
                category_id=category.id,
                name="Cover Item ID",
                data_type="text",
                plugin_field_key="cover_item_id",
            )
            session.add_all([genre_attr, read_attr, tags_attr, cover_attr])
            await session.flush()

            metadata_rows: list[ItemMetadata] = []
            for index in range(1, 1002):
                item_id = f"item-{index}"
                session.add(_build_item(account_id=account.id, item_id=item_id, name=f"Comic-{index}.cbz", now=now))
                metadata_rows.append(
                    ItemMetadata(
                        account_id=account.id,
                        item_id=item_id,
                        category_id=category.id,
                        values={
                            str(genre_attr.id): "Sci-Fi",
                            str(read_attr.id): index % 2 == 0,
                            str(tags_attr.id): ["space", "space", "award"] if index <= 600 else ["award"],
                            str(cover_attr.id): f"cover-{index}",
                        },
                    )
                )
            session.add_all(metadata_rows)
            await session.commit()

            dashboard = await MetadataQueryService(session).get_category_dashboard(category_id=category.id)

            assert dashboard.total_items == 1001
            assert dashboard.average_coverage == 100
            assert dashboard.fields_with_gaps == 0
            assert len(dashboard.cards) == 3
            assert all(card.attribute_id != cover_attr.id for card in dashboard.cards)

            genre_card = next(card for card in dashboard.cards if card.attribute_id == genre_attr.id)
            assert genre_card.chart_type == "count"
            assert genre_card.filled_count == 1001
            assert genre_card.distinct_count == 1
            assert [(point.label, point.count) for point in genre_card.points] == [("Sci-Fi", 1001)]

            read_card = next(card for card in dashboard.cards if card.attribute_id == read_attr.id)
            assert read_card.chart_type == "pie"
            assert read_card.filled_count == 1001
            assert read_card.distinct_count == 2
            assert [(point.value, point.count) for point in read_card.points] == [("true", 500), ("false", 501)]

            tags_card = next(card for card in dashboard.cards if card.attribute_id == tags_attr.id)
            assert tags_card.chart_type == "count"
            assert tags_card.filled_count == 1001
            assert tags_card.distinct_count == 2
            assert [(point.label, point.count) for point in tags_card.points] == [("award", 1001), ("space", 600)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_metadata_dashboard_query_limits_text_and_tags_cards_to_top_values():
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
            account = _build_account(now)
            category = MetadataCategory(name="Top Text Dashboard Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            title_attr = MetadataAttribute(category_id=category.id, name="Title", data_type="text")
            tags_attr = MetadataAttribute(category_id=category.id, name="Tags", data_type="tags")
            session.add_all([title_attr, tags_attr])
            await session.flush()

            item_index = 0
            for bucket_index in range(1, 21):
                label = f"Value {bucket_index:02d}"
                repeat_count = 21 - bucket_index
                for _ in range(repeat_count):
                    item_index += 1
                    item_id = f"text-item-{item_index}"
                    session.add(_build_item(account_id=account.id, item_id=item_id, name=f"Text-{item_index}.cbz", now=now))
                    session.add(
                        ItemMetadata(
                            account_id=account.id,
                            item_id=item_id,
                            category_id=category.id,
                            values={
                                str(title_attr.id): label,
                                str(tags_attr.id): [label],
                            },
                        )
                    )
            await session.commit()

            dashboard = await MetadataQueryService(session).get_category_dashboard(category_id=category.id)

            assert dashboard.total_items == 210
            assert len(dashboard.cards) == 2

            title_card = next(card for card in dashboard.cards if card.attribute_id == title_attr.id)
            assert title_card.attribute_id == title_attr.id
            assert title_card.chart_type == "count"
            assert title_card.distinct_count == 20
            assert len(title_card.points) == 10
            assert [(point.label, point.count) for point in title_card.points[:3]] == [
                ("Value 01", 20),
                ("Value 02", 19),
                ("Value 03", 18),
            ]
            assert [(point.label, point.count) for point in title_card.points[-2:]] == [
                ("Value 09", 12),
                ("Value 10", 11),
            ]

            tags_card = next(card for card in dashboard.cards if card.attribute_id == tags_attr.id)
            assert tags_card.attribute_id == tags_attr.id
            assert tags_card.chart_type == "count"
            assert tags_card.distinct_count == 20
            assert len(tags_card.points) == 10
            assert [(point.label, point.count) for point in tags_card.points[:3]] == [
                ("Value 01", 20),
                ("Value 02", 19),
                ("Value 03", 18),
            ]
            assert [(point.label, point.count) for point in tags_card.points[-2:]] == [
                ("Value 09", 12),
                ("Value 10", 11),
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_metadata_dashboard_query_uses_exact_counts_and_histograms_for_numbers():
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
            account = _build_account(now)
            category = MetadataCategory(name="Numeric Dashboard Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            volume_attr = MetadataAttribute(
                category_id=category.id,
                name="Volume",
                data_type="number",
                plugin_field_key="volume",
            )
            year_attr = MetadataAttribute(
                category_id=category.id,
                name="Year",
                data_type="number",
                plugin_field_key="year",
            )
            page_count_attr = MetadataAttribute(
                category_id=category.id,
                name="Page Count",
                data_type="number",
                plugin_field_key="page_count",
            )
            session.add_all([volume_attr, year_attr, page_count_attr])
            await session.flush()

            page_counts = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, None]
            for index, page_count in enumerate(page_counts, start=1):
                item_id = f"numeric-item-{index}"
                session.add(_build_item(account_id=account.id, item_id=item_id, name=f"Number-{index}.cbz", now=now))
                values = {
                    str(volume_attr.id): (index % 3) + 1,
                    str(year_attr.id): 2024 + (index % 2),
                }
                if page_count is not None:
                    values[str(page_count_attr.id)] = page_count
                session.add(
                    ItemMetadata(
                        account_id=account.id,
                        item_id=item_id,
                        category_id=category.id,
                        values=values,
                    )
                )
            await session.commit()

            dashboard = await MetadataQueryService(session).get_category_dashboard(category_id=category.id)

            assert dashboard.total_items == 14
            assert dashboard.fields_with_gaps == 1

            volume_card = next(card for card in dashboard.cards if card.attribute_id == volume_attr.id)
            assert volume_card.chart_type == "count"
            assert [(point.value, point.count) for point in volume_card.points] == [("1", 4), ("2", 5), ("3", 5)]

            year_card = next(card for card in dashboard.cards if card.attribute_id == year_attr.id)
            assert year_card.chart_type == "count"
            assert [(point.value, point.count) for point in year_card.points] == [("2024", 7), ("2025", 7)]

            page_count_card = next(card for card in dashboard.cards if card.attribute_id == page_count_attr.id)
            assert page_count_card.chart_type == "histogram"
            assert page_count_card.filled_count == 13
            assert page_count_card.distinct_count == 13
            assert [stat.key for stat in page_count_card.stats] == ["min", "max", "average"]
            assert page_count_card.stats[0].value == "10"
            assert page_count_card.stats[1].value == "130"
            assert page_count_card.points[0].range_start == 10
            assert page_count_card.points[0].range_end == 20
            assert page_count_card.points[-1].range_start == 120
            assert page_count_card.points[-1].range_end == 130
            assert page_count_card.points[-1].count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_metadata_dashboard_query_uses_histogram_for_high_cardinality_exact_number_fields():
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
            account = _build_account(now)
            category = MetadataCategory(name="High Cardinality Numeric Dashboard Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            year_attr = MetadataAttribute(
                category_id=category.id,
                name="Year",
                data_type="number",
                plugin_field_key="year",
            )
            session.add(year_attr)
            await session.flush()

            for index, year in enumerate(range(1967, 2020), start=1):
                item_id = f"year-item-{index}"
                session.add(_build_item(account_id=account.id, item_id=item_id, name=f"Year-{index}.cbz", now=now))
                session.add(
                    ItemMetadata(
                        account_id=account.id,
                        item_id=item_id,
                        category_id=category.id,
                        values={
                            str(year_attr.id): year,
                        },
                    )
                )
            await session.commit()

            dashboard = await MetadataQueryService(session).get_category_dashboard(category_id=category.id)

            assert dashboard.total_items == 53

            year_card = dashboard.cards[0]
            assert year_card.attribute_id == year_attr.id
            assert year_card.chart_type == "histogram"
            assert year_card.distinct_count == 53
            assert len(year_card.points) < year_card.distinct_count
            assert [stat.value for stat in year_card.stats] == ["1967", "2019", "1993"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_metadata_dashboard_query_groups_dates_by_month_or_year():
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
            account = _build_account(now)
            category = MetadataCategory(name="Date Dashboard Category", is_active=True)
            session.add_all([account, category])
            await session.flush()

            release_attr = MetadataAttribute(category_id=category.id, name="Release Date", data_type="date")
            archive_attr = MetadataAttribute(category_id=category.id, name="Archive Date", data_type="date")
            session.add_all([release_attr, archive_attr])
            await session.flush()

            values_by_item = [
                ("2025-01-05", "2020-01-01"),
                ("2025-02-10", "2022-01-01"),
                ("2026-06-15", "2024-01-01"),
                ("2026-07-20", "2024-08-01"),
            ]
            for index, (release_date, archive_date) in enumerate(values_by_item, start=1):
                item_id = f"date-item-{index}"
                session.add(_build_item(account_id=account.id, item_id=item_id, name=f"Date-{index}.cbz", now=now))
                session.add(
                    ItemMetadata(
                        account_id=account.id,
                        item_id=item_id,
                        category_id=category.id,
                        values={
                            str(release_attr.id): release_date,
                            str(archive_attr.id): archive_date,
                        },
                    )
                )
            await session.commit()

            dashboard = await MetadataQueryService(session).get_category_dashboard(category_id=category.id)

            release_card = next(card for card in dashboard.cards if card.attribute_id == release_attr.id)
            assert release_card.chart_type == "count"
            assert [point.value for point in release_card.points] == ["2025-01", "2025-02", "2026-06", "2026-07"]
            assert [stat.value for stat in release_card.stats] == [
                "2025-01-05T00:00:00+00:00",
                "2026-07-20T00:00:00+00:00",
            ]

            archive_card = next(card for card in dashboard.cards if card.attribute_id == archive_attr.id)
            assert archive_card.chart_type == "count"
            assert [point.value for point in archive_card.points] == ["2020", "2022", "2024"]
            assert [point.count for point in archive_card.points] == [1, 1, 2]
            assert [stat.value for stat in archive_card.stats] == [
                "2020-01-01T00:00:00+00:00",
                "2024-08-01T00:00:00+00:00",
            ]
    finally:
        await engine.dispose()
