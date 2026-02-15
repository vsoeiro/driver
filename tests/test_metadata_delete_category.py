from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.sql.dml import Delete

from backend.api.routes.metadata import delete_category
from backend.db.models import MetadataCategory


@pytest.mark.asyncio
async def test_delete_category_removes_item_metadata_and_category():
    category_id = uuid4()
    session = AsyncMock()
    category = MetadataCategory(id=category_id, name="Comic", description=None)
    session.get.return_value = category

    await delete_category(category_id, session)

    assert session.execute.await_count == 1
    stmt = session.execute.await_args.args[0]
    assert isinstance(stmt, Delete)
    assert stmt.table.name == "item_metadata"
    session.delete.assert_awaited_once_with(category)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_category_not_found():
    category_id = uuid4()
    session = AsyncMock()
    session.get.return_value = None

    with pytest.raises(HTTPException) as exc:
        await delete_category(category_id, session)

    assert exc.value.status_code == 404
    assert session.execute.await_count == 0
    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()
