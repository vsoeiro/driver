from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.services.metadata_libraries.books import metadata_service as books_metadata
from backend.services.metadata_libraries.comics import metadata_service as comics_metadata


@pytest.mark.asyncio
async def test_comic_force_remap_moves_existing_cover_between_accounts_without_downloading(monkeypatch):
    session = AsyncMock()
    service = comics_metadata.ComicMetadataService(session)
    source_account_id = uuid4()
    old_cover_account_id = uuid4()
    target_cover_account_id = uuid4()
    source_client = SimpleNamespace(download_file_to_path=AsyncMock())
    old_cover_account = SimpleNamespace(id=old_cover_account_id)
    target_cover_account = SimpleNamespace(id=target_cover_account_id)
    old_cover_client = SimpleNamespace()
    target_cover_client = SimpleNamespace(
        get_item_metadata=AsyncMock(
            return_value=SimpleNamespace(id="cover-new", name="item-1.jpg")
        )
    )
    transfer_cover = AsyncMock(return_value="cover-new")
    apply_change = AsyncMock()

    async def fake_get_linked_account(account_id):
        if str(account_id) == str(old_cover_account_id):
            return old_cover_account
        return None

    monkeypatch.setattr(service, "_get_linked_account", fake_get_linked_account)
    monkeypatch.setattr(
        comics_metadata,
        "build_drive_client",
        lambda account, token_manager: old_cover_client,
    )
    monkeypatch.setattr(
        comics_metadata,
        "DriveTransferService",
        lambda: SimpleNamespace(transfer_file_between_accounts=transfer_cover),
    )
    monkeypatch.setattr(comics_metadata, "apply_metadata_change", apply_change)

    outcome = await service._process_single_file(
        source_client=source_client,
        source_account=SimpleNamespace(id=source_account_id),
        source_account_pk=source_account_id,
        source_account_id=str(source_account_id),
        cover_client=target_cover_client,
        cover_account=target_cover_account,
        item=SimpleNamespace(id="item-1", name="Comic.cbz", extension="cbz"),
        cover_folder_id="covers-target",
        category_id=uuid4(),
        attr_ids={
            "cover_item_id": "attr-cover-id",
            "cover_account_id": "attr-cover-account",
            "cover_filename": "attr-cover-name",
        },
        cover_settings=SimpleNamespace(
            max_width=700,
            max_height=1050,
            target_bytes=250000,
            quality_steps=(84, 78, 72),
        ),
        job_id=None,
        batch_id=None,
        force_remap=True,
        existing_metadata_values={
            "attr-cover-id": "cover-old",
            "attr-cover-account": str(old_cover_account_id),
            "attr-cover-name": "item-1.jpg",
            "attr-page-count": 12,
        },
    )

    assert outcome.mapped is True
    source_client.download_file_to_path.assert_not_awaited()
    transfer_cover.assert_awaited_once_with(
        source_client=old_cover_client,
        destination_client=target_cover_client,
        source_account=old_cover_account,
        destination_account=target_cover_account,
        source_item_id="cover-old",
        source_item_name="item-1.jpg",
        destination_folder_id="covers-target",
    )
    apply_change.assert_awaited_once()
    values = apply_change.await_args.kwargs["values"]
    assert values["attr-cover-id"] == "cover-new"
    assert values["attr-cover-account"] == str(target_cover_account_id)
    assert values["attr-cover-name"] == "item-1.jpg"
    assert values["attr-page-count"] == 12


@pytest.mark.asyncio
async def test_book_force_remap_skips_when_existing_cover_is_already_in_target_folder(monkeypatch):
    session = AsyncMock()
    service = books_metadata.BookMetadataService(session)
    source_client = SimpleNamespace(download_file_to_path=AsyncMock())
    cover_account_id = uuid4()
    cover_account = SimpleNamespace(id=cover_account_id)
    cover_client = SimpleNamespace()
    existing_cover_client = SimpleNamespace(
        get_item_path=AsyncMock(
            return_value=[
                {"id": "root", "name": "Root"},
                {"id": "covers-target", "name": "__driver_comic_covers__"},
                {"id": "cover-1", "name": "item-1.jpg"},
            ]
        )
    )

    session.get = AsyncMock(return_value=cover_account)
    monkeypatch.setattr(
        books_metadata,
        "build_drive_client",
        lambda account, token_manager: existing_cover_client,
    )
    apply_change = AsyncMock()
    monkeypatch.setattr(books_metadata, "apply_metadata_change", apply_change)

    result = await service._process_single_file(
        source_client=source_client,
        source_account=SimpleNamespace(id=uuid4()),
        cover_client=cover_client,
        cover_account=cover_account,
        item=SimpleNamespace(id="item-1", name="Book.epub", extension="epub"),
        cover_folder_id="covers-target",
        category_id=uuid4(),
        attr_ids={
            "cover_item_id": "attr-cover-id",
            "cover_account_id": "attr-cover-account",
            "cover_filename": "attr-cover-name",
        },
        cover_settings=SimpleNamespace(
            max_width=700,
            max_height=1050,
            target_bytes=250000,
            quality_steps=(84, 78, 72),
        ),
        job_id=None,
        batch_id=None,
        force_remap=True,
        existing_metadata_values={
            "attr-cover-id": "cover-1",
            "attr-cover-account": str(cover_account_id),
            "attr-cover-name": "item-1.jpg",
        },
    )

    assert result is False
    source_client.download_file_to_path.assert_not_awaited()
    apply_change.assert_not_awaited()


@pytest.mark.asyncio
async def test_comic_force_remap_preserves_existing_metadata_fields_when_reextracting(monkeypatch):
    session = AsyncMock()
    service = comics_metadata.ComicMetadataService(session)
    source_account_id = uuid4()
    cover_account_id = uuid4()
    source_client = SimpleNamespace(download_file_to_path=AsyncMock())
    cover_client = SimpleNamespace(
        upload_small_file=AsyncMock(
            return_value=SimpleNamespace(id="cover-new", name="item-1.jpg")
        )
    )
    apply_change = AsyncMock()

    monkeypatch.setattr(
        comics_metadata,
        "extract_comic_asset",
        lambda path, ext: SimpleNamespace(
            cover_bytes=b"cover",
            cover_extension="jpg",
            page_count=12,
            format="cbz",
            details={},
        ),
    )
    monkeypatch.setattr(
        comics_metadata,
        "optimize_cover_image",
        lambda *args, **kwargs: (b"optimized", "jpg", {}),
    )
    monkeypatch.setattr(comics_metadata, "apply_metadata_change", apply_change)

    outcome = await service._process_single_file(
        source_client=source_client,
        source_account=SimpleNamespace(id=source_account_id),
        source_account_pk=source_account_id,
        source_account_id=str(source_account_id),
        cover_client=cover_client,
        cover_account=SimpleNamespace(id=cover_account_id),
        item=SimpleNamespace(id="item-1", name="Comic.cbz", extension="cbz"),
        cover_folder_id="covers-target",
        category_id=uuid4(),
        attr_ids={
            "series": "attr-series",
            "volume": "attr-volume",
            "file_format": "attr-format",
            "page_count": "attr-page-count",
            "cover_item_id": "attr-cover-id",
            "cover_account_id": "attr-cover-account",
            "cover_filename": "attr-cover-name",
        },
        cover_settings=SimpleNamespace(
            max_width=700,
            max_height=1050,
            target_bytes=250000,
            quality_steps=(84, 78, 72),
        ),
        job_id=None,
        batch_id=None,
        force_remap=True,
        existing_metadata_values={
            "attr-series": "Yoko Tsuno",
            "attr-volume": "31",
        },
    )

    assert outcome.mapped is True
    apply_change.assert_awaited_once()
    values = apply_change.await_args.kwargs["values"]
    assert values["attr-series"] == "Yoko Tsuno"
    assert values["attr-volume"] == "31"
    assert values["attr-format"] == "cbz"
    assert values["attr-page-count"] == 12
    assert values["attr-cover-id"] == "cover-new"
    assert values["attr-cover-account"] == str(cover_account_id)
    assert values["attr-cover-name"] == "item-1.jpg"


@pytest.mark.asyncio
async def test_comic_extract_preserves_existing_metadata_fields_when_mapping_assets(monkeypatch):
    session = AsyncMock()
    service = comics_metadata.ComicMetadataService(session)
    source_account_id = uuid4()
    cover_account_id = uuid4()
    source_client = SimpleNamespace(download_file_to_path=AsyncMock())
    cover_client = SimpleNamespace(
        upload_small_file=AsyncMock(
            return_value=SimpleNamespace(id="cover-new", name="item-1.jpg")
        )
    )
    apply_change = AsyncMock()

    monkeypatch.setattr(
        service,
        "_existing_mapping_skip_reason",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        comics_metadata,
        "extract_comic_asset",
        lambda path, ext: SimpleNamespace(
            cover_bytes=b"cover",
            cover_extension="jpg",
            page_count=12,
            format="cbz",
            details={},
        ),
    )
    monkeypatch.setattr(
        comics_metadata,
        "optimize_cover_image",
        lambda *args, **kwargs: (b"optimized", "jpg", {}),
    )
    monkeypatch.setattr(comics_metadata, "apply_metadata_change", apply_change)

    outcome = await service._process_single_file(
        source_client=source_client,
        source_account=SimpleNamespace(id=source_account_id),
        source_account_pk=source_account_id,
        source_account_id=str(source_account_id),
        cover_client=cover_client,
        cover_account=SimpleNamespace(id=cover_account_id),
        item=SimpleNamespace(id="item-1", name="Comic.cbz", extension="cbz"),
        cover_folder_id="covers-target",
        category_id=uuid4(),
        attr_ids={
            "series": "attr-series",
            "volume": "attr-volume",
            "file_format": "attr-format",
            "page_count": "attr-page-count",
            "cover_item_id": "attr-cover-id",
            "cover_account_id": "attr-cover-account",
            "cover_filename": "attr-cover-name",
        },
        cover_settings=SimpleNamespace(
            max_width=700,
            max_height=1050,
            target_bytes=250000,
            quality_steps=(84, 78, 72),
        ),
        job_id=None,
        batch_id=None,
        force_remap=False,
        existing_metadata_values={
            "attr-series": "Yoko Tsuno",
            "attr-volume": "31",
        },
    )

    assert outcome.mapped is True
    apply_change.assert_awaited_once()
    values = apply_change.await_args.kwargs["values"]
    assert values["attr-series"] == "Yoko Tsuno"
    assert values["attr-volume"] == "31"
    assert values["attr-format"] == "cbz"
    assert values["attr-page-count"] == 12
    assert values["attr-cover-id"] == "cover-new"
    assert values["attr-cover-account"] == str(cover_account_id)
    assert values["attr-cover-name"] == "item-1.jpg"


@pytest.mark.asyncio
async def test_book_force_remap_preserves_existing_title_when_reextracting(monkeypatch):
    session = AsyncMock()
    service = books_metadata.BookMetadataService(session)
    source_account_id = uuid4()
    cover_account_id = uuid4()
    source_client = SimpleNamespace(download_file_to_path=AsyncMock())
    cover_client = SimpleNamespace(
        upload_small_file=AsyncMock(
            return_value=SimpleNamespace(id="cover-new", name="item-1.jpg")
        )
    )
    apply_change = AsyncMock()

    monkeypatch.setattr(
        books_metadata,
        "extract_comic_asset",
        lambda path, ext: SimpleNamespace(
            cover_bytes=b"cover",
            cover_extension="jpg",
            page_count=42,
            format="epub",
        ),
    )
    monkeypatch.setattr(
        books_metadata,
        "optimize_cover_image",
        lambda *args, **kwargs: (b"optimized", "jpg", {}),
    )
    monkeypatch.setattr(books_metadata, "apply_metadata_change", apply_change)

    result = await service._process_single_file(
        source_client=source_client,
        source_account=SimpleNamespace(id=source_account_id),
        cover_client=cover_client,
        cover_account=SimpleNamespace(id=cover_account_id),
        item=SimpleNamespace(id="item-1", name="Book.epub", extension="epub"),
        cover_folder_id="covers-target",
        category_id=uuid4(),
        attr_ids={
            "title": "attr-title",
            "author": "attr-author",
            "file_format": "attr-format",
            "page_count": "attr-page-count",
            "cover_item_id": "attr-cover-id",
            "cover_account_id": "attr-cover-account",
            "cover_filename": "attr-cover-name",
        },
        cover_settings=SimpleNamespace(
            max_width=700,
            max_height=1050,
            target_bytes=250000,
            quality_steps=(84, 78, 72),
        ),
        job_id=None,
        batch_id=None,
        force_remap=True,
        existing_metadata_values={
            "attr-title": "Manual Title",
            "attr-author": "Manual Author",
        },
    )

    assert result is True
    apply_change.assert_awaited_once()
    values = apply_change.await_args.kwargs["values"]
    assert values["attr-title"] == "Manual Title"
    assert values["attr-author"] == "Manual Author"
    assert values["attr-format"] == "epub"
    assert values["attr-page-count"] == 42
    assert values["attr-cover-id"] == "cover-new"
    assert values["attr-cover-account"] == str(cover_account_id)
    assert values["attr-cover-name"] == "item-1.jpg"


@pytest.mark.asyncio
async def test_book_extract_preserves_existing_manual_fields_when_mapping_assets(monkeypatch):
    session = AsyncMock()
    service = books_metadata.BookMetadataService(session)
    source_account_id = uuid4()
    cover_account_id = uuid4()
    source_client = SimpleNamespace(download_file_to_path=AsyncMock())
    cover_client = SimpleNamespace(
        upload_small_file=AsyncMock(
            return_value=SimpleNamespace(id="cover-new", name="item-1.jpg")
        )
    )
    apply_change = AsyncMock()

    monkeypatch.setattr(
        service,
        "_is_conflicting_or_already_mapped",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        books_metadata,
        "extract_comic_asset",
        lambda path, ext: SimpleNamespace(
            cover_bytes=b"cover",
            cover_extension="jpg",
            page_count=42,
            format="epub",
        ),
    )
    monkeypatch.setattr(
        books_metadata,
        "optimize_cover_image",
        lambda *args, **kwargs: (b"optimized", "jpg", {}),
    )
    monkeypatch.setattr(books_metadata, "apply_metadata_change", apply_change)

    result = await service._process_single_file(
        source_client=source_client,
        source_account=SimpleNamespace(id=source_account_id),
        cover_client=cover_client,
        cover_account=SimpleNamespace(id=cover_account_id),
        item=SimpleNamespace(id="item-1", name="Book.epub", extension="epub"),
        cover_folder_id="covers-target",
        category_id=uuid4(),
        attr_ids={
            "title": "attr-title",
            "author": "attr-author",
            "file_format": "attr-format",
            "page_count": "attr-page-count",
            "cover_item_id": "attr-cover-id",
            "cover_account_id": "attr-cover-account",
            "cover_filename": "attr-cover-name",
        },
        cover_settings=SimpleNamespace(
            max_width=700,
            max_height=1050,
            target_bytes=250000,
            quality_steps=(84, 78, 72),
        ),
        job_id=None,
        batch_id=None,
        force_remap=False,
        existing_metadata_values={
            "attr-title": "Manual Title",
            "attr-author": "Manual Author",
        },
    )

    assert result is True
    apply_change.assert_awaited_once()
    values = apply_change.await_args.kwargs["values"]
    assert values["attr-title"] == "Manual Title"
    assert values["attr-author"] == "Manual Author"
    assert values["attr-format"] == "epub"
    assert values["attr-page-count"] == 42
    assert values["attr-cover-id"] == "cover-new"
    assert values["attr-cover-account"] == str(cover_account_id)
    assert values["attr-cover-name"] == "item-1.jpg"
