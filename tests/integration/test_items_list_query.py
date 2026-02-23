from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.application.metadata.item_query_service import ItemQueryService
from backend.db.models import Base, Item, ItemMetadata, LinkedAccount, MetadataAttribute, MetadataCategory


@pytest.mark.asyncio
async def test_items_list_query_filters_sort_pagination_and_total():
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
            category = MetadataCategory(name="Comics", is_active=True)
            session.add_all([account, category])
            await session.flush()

            series_attr = MetadataAttribute(
                category_id=category.id,
                name="Series",
                data_type="text",
            )
            session.add(series_attr)
            await session.flush()

            item_alpha = Item(
                account_id=account.id,
                item_id="item-1",
                parent_id="root",
                name="Alpha.cbz",
                path="/Comics/Alpha.cbz",
                item_type="file",
                extension="cbz",
                size=100,
                created_at=now,
                modified_at=now,
            )
            item_beta = Item(
                account_id=account.id,
                item_id="item-2",
                parent_id="root",
                name="Beta.cbz",
                path="/Comics/Beta.cbz",
                item_type="file",
                extension="cbz",
                size=200,
                created_at=now,
                modified_at=now,
            )
            item_zulu = Item(
                account_id=account.id,
                item_id="item-3",
                parent_id="root",
                name="Zulu.cbz",
                path="/Comics/Zulu.cbz",
                item_type="file",
                extension="cbz",
                size=300,
                created_at=now,
                modified_at=now,
            )
            session.add_all([item_alpha, item_beta, item_zulu])
            await session.flush()

            session.add_all(
                [
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-1",
                        category_id=category.id,
                        values={str(series_attr.id): "Saga"},
                    ),
                    ItemMetadata(
                        account_id=account.id,
                        item_id="item-2",
                        category_id=category.id,
                        values={str(series_attr.id): "Saga"},
                    ),
                ]
            )
            await session.commit()

            service = ItemQueryService(session)
            response = await service.list_items(
                page=2,
                page_size=1,
                sort_by="name",
                sort_order="asc",
                metadata_sort_attribute_id=None,
                metadata_sort_data_type=None,
                q=None,
                search_fields="both",
                path_prefix=None,
                direct_children_only=False,
                extensions=None,
                item_type="file",
                size_min=None,
                size_max=None,
                account_id=account.id,
                category_id=category.id,
                has_metadata=True,
                metadata_filters=json.dumps({str(series_attr.id): {"op": "eq", "value": "Saga"}}),
                include_total=True,
            )

            assert response.total == 2
            assert response.total_pages == 2
            assert len(response.items) == 1
            assert response.items[0].name == "Beta.cbz"
            assert response.items[0].metadata is not None
            assert response.items[0].metadata.category_name == "Comics"
    finally:
        await engine.dispose()
