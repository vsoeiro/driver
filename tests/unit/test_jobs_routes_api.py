import io
import tempfile
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from backend.api.routes import jobs as jobs_routes
from backend.domain.errors import DomainError, NotFoundError
from backend.schemas.jobs import (
    JobAnalyzeImageAssetsRequest,
    JobAnalyzeLibraryImageAssetsRequest,
    JobApplyMetadataRecursiveRequest,
    JobApplyRuleRequest,
    JobExtractBookAssetsRequest,
    JobExtractComicAssetsRequest,
    JobExtractLibraryBookAssetsRequest,
    JobExtractLibraryComicAssetsRequest,
    JobMapLibraryBooksRequest,
    JobMetadataUpdateRequest,
    JobMoveRequest,
    JobReindexComicCoversRequest,
    JobRemoveDuplicateFilesRequest,
    JobRemoveMetadataRecursiveRequest,
    JobSyncRequest,
    JobUndoMetadataBatchRequest,
)


def _make_request(query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/jobs",
        "headers": [],
        "query_string": query_string.encode(),
        "scheme": "http",
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }
    return Request(scope)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_fetch_rows_with_limit_and_filename_sanitization(monkeypatch):
    db = SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([("row-1",), ("row-2",)])))
    monkeypatch.setattr(jobs_routes, "MAX_LIBRARY_SCAN_ROWS", 2)

    rows = await jobs_routes._fetch_rows_with_limit(db, stmt=SimpleNamespace(limit=lambda value: value), operation_name="scan")

    assert rows == [("row-1",), ("row-2",)]
    assert jobs_routes._sanitize_upload_filename("../covers/comic.cbz") == "comic.cbz"
    assert jobs_routes._sanitize_upload_filename("  ") == "upload.bin"


@pytest.mark.asyncio
async def test_fetch_rows_with_limit_rejects_oversized_scans(monkeypatch):
    db = SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([("row-1",), ("row-2",), ("row-3",)])))
    monkeypatch.setattr(jobs_routes, "MAX_LIBRARY_SCAN_ROWS", 2)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_routes._fetch_rows_with_limit(
            db,
            stmt=SimpleNamespace(limit=lambda value: value),
            operation_name="scan",
        )

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_list_jobs_normalizes_status_and_type_filters():
    job_service = SimpleNamespace(get_jobs=AsyncMock(return_value=["job-1"]))
    request = _make_request("status[]=queued&status[]=done,failed&type[]=sync_items&type=apply_rule")

    result = await jobs_routes.list_jobs(
        request,
        job_service,
        limit=25,
        offset=10,
        include_estimates=False,
        status_filter=["pending, running"],
        type_filter=["upload_file", "apply_rule"],
        created_after=None,
    )

    assert result == ["job-1"]
    job_service.get_jobs.assert_awaited_once_with(
        limit=25,
        offset=10,
        statuses=["PENDING", "RUNNING", "QUEUED", "DONE", "FAILED"],
        job_types=["upload_file", "apply_rule", "sync_items"],
        created_after=None,
        include_estimates=False,
    )


@pytest.mark.asyncio
async def test_filter_helpers_exclude_mapped_and_conflicting_items():
    account_id = uuid4()
    category_id = uuid4()
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            _RowsResult(["item-2"]),
            _RowsResult([
                ("item-1", category_id),
                ("item-2", uuid4()),
            ]),
        ])
    )

    without_category = await jobs_routes._filter_items_without_category(
        db,
        {account_id: ["item-1", "item-2"]},
        category_id=category_id,
    )
    without_conflicts = await jobs_routes._filter_items_without_conflicting_metadata(
        db,
        {account_id: ["item-1", "item-2"]},
        category_id=category_id,
    )

    assert without_category == {account_id: ["item-1"]}
    assert without_conflicts == {account_id: ["item-1"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "request_factory", "service_factory", "expected_job_type"),
    [
        (
            jobs_routes.create_move_job,
            lambda: JobMoveRequest(
                source_account_id=uuid4(),
                source_item_id="item-1",
                destination_account_id=uuid4(),
                destination_folder_id="folder-1",
            ),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "move_items",
        ),
        (
            jobs_routes.create_metadata_update_job,
            lambda: JobMetadataUpdateRequest(
                account_id=uuid4(),
                root_item_id="root-1",
                metadata={"Title": "Saga"},
                category_name="Comics",
            ),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "update_metadata",
        ),
        (
            jobs_routes.create_sync_job,
            lambda: JobSyncRequest(account_id=uuid4()),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "sync_items",
        ),
        (
            jobs_routes.create_apply_metadata_recursive_job,
            lambda: JobApplyMetadataRecursiveRequest(
                account_id=uuid4(),
                path_prefix="/Library",
                category_id=uuid4(),
                values={"title": "Saga"},
                include_folders=True,
            ),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "apply_metadata_recursive",
        ),
        (
            jobs_routes.create_remove_metadata_recursive_job,
            lambda: JobRemoveMetadataRecursiveRequest(
                account_id=uuid4(),
                path_prefix="/Library",
            ),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "remove_metadata_recursive",
        ),
        (
            jobs_routes.create_remove_duplicates_job,
            lambda: JobRemoveDuplicateFilesRequest(
                preferred_account_id=uuid4(),
                account_id=uuid4(),
                scope="cross_account",
                extensions=["cbz"],
            ),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "remove_duplicate_files",
        ),
        (
            jobs_routes.create_metadata_undo_job,
            lambda: JobUndoMetadataBatchRequest(batch_id=uuid4()),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "undo_metadata_batch",
        ),
        (
            jobs_routes.create_apply_rule_job,
            lambda: JobApplyRuleRequest(rule_id=uuid4()),
            lambda session: {"job_service": SimpleNamespace(session=session)},
            "apply_metadata_rule",
        ),
    ],
)
async def test_simple_enqueue_routes_forward_payload(func, request_factory, service_factory, expected_job_type, monkeypatch):
    session = object()
    job = SimpleNamespace(id=uuid4())
    enqueue_mock = AsyncMock(return_value=job)
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", enqueue_mock)

    payload_request = request_factory()
    result = await func(payload_request, **service_factory(session))

    assert result is job
    enqueue_mock.assert_awaited_once_with(
        session,
        job_type=expected_job_type,
        payload=payload_request.model_dump(mode="json"),
    )


@pytest.mark.asyncio
async def test_create_upload_job_persists_temp_file_and_enqueues(monkeypatch, tmp_path):
    job_service = SimpleNamespace(session=object())
    enqueue_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", enqueue_mock)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(uuid, "uuid4", lambda: UUID("11111111-1111-1111-1111-111111111111"))

    file = UploadFile(filename="../comic.cbz", file=io.BytesIO(b"archive-bytes"))

    result = await jobs_routes.create_upload_job(
        job_service,
        file=file,
        account_id="acc-1",
        folder_id="folder-1",
    )

    assert result.id
    temp_files = list((tmp_path / "onedrive_uploads").glob("*_comic.cbz"))
    assert len(temp_files) == 1
    assert temp_files[0].read_bytes() == b"archive-bytes"
    payload = enqueue_mock.await_args.kwargs["payload"]
    assert payload["filename"] == "comic.cbz"
    assert payload["folder_id"] == "folder-1"


@pytest.mark.asyncio
async def test_create_upload_job_removes_temp_file_when_enqueue_fails(monkeypatch, tmp_path):
    job_service = SimpleNamespace(session=object())
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(uuid, "uuid4", lambda: UUID("22222222-2222-2222-2222-222222222222"))

    with pytest.raises(RuntimeError):
        await jobs_routes.create_upload_job(
            job_service,
            file=UploadFile(filename="comic.cbz", file=io.BytesIO(b"archive-bytes")),
            account_id="acc-1",
            folder_id="folder-1",
        )

    assert list((tmp_path / "onedrive_uploads").glob("*")) == []


@pytest.mark.asyncio
async def test_create_extract_and_analyze_routes_validate_active_libraries(monkeypatch):
    db = object()
    enqueue_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    validate_mock = AsyncMock()
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", enqueue_mock)
    monkeypatch.setattr(jobs_routes, "_validate_selected_extensions", validate_mock)

    comic_request = JobExtractComicAssetsRequest(account_id=uuid4(), item_ids=["item-1"])
    comic_job = await jobs_routes.create_extract_comic_assets_job(comic_request, db)
    assert comic_job.id
    validate_mock.assert_awaited_once()

    monkeypatch.setattr(
        jobs_routes,
        "MetadataLibraryService",
        lambda db_session: SimpleNamespace(
            get_active_books_category=AsyncMock(return_value=SimpleNamespace(plugin_key=jobs_routes.BOOKS_LIBRARY_KEY)),
            get_active_images_category=AsyncMock(return_value=SimpleNamespace(plugin_key=jobs_routes.IMAGES_LIBRARY_KEY)),
        ),
    )

    await jobs_routes.create_extract_book_assets_job(
        JobExtractBookAssetsRequest(account_id=uuid4(), item_ids=["book-1"]),
        db,
    )
    await jobs_routes.create_analyze_image_assets_job(
        JobAnalyzeImageAssetsRequest(account_id=uuid4(), item_ids=["image-1"]),
        db,
    )

    assert enqueue_mock.await_count == 3


@pytest.mark.asyncio
async def test_create_extract_and_analyze_routes_reject_inactive_libraries(monkeypatch):
    db = object()
    monkeypatch.setattr(
        jobs_routes,
        "MetadataLibraryService",
        lambda db_session: SimpleNamespace(
            get_active_books_category=AsyncMock(return_value=None),
            get_active_images_category=AsyncMock(return_value=SimpleNamespace(plugin_key="wrong")),
        ),
    )

    with pytest.raises(HTTPException) as books_exc:
        await jobs_routes.create_extract_book_assets_job(
            JobExtractBookAssetsRequest(account_id=uuid4(), item_ids=["book-1"]),
            db,
        )
    with pytest.raises(HTTPException) as images_exc:
        await jobs_routes.create_analyze_image_assets_job(
            JobAnalyzeImageAssetsRequest(account_id=uuid4(), item_ids=["image-1"]),
            db,
        )

    assert books_exc.value.status_code == 400
    assert images_exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_analyze_library_image_assets_job_chunks_items(monkeypatch):
    account_a = uuid4()
    account_b = uuid4()
    image_category = SimpleNamespace(id=uuid4())
    enqueue_mock = AsyncMock(side_effect=[
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    ])
    monkeypatch.setattr(
        jobs_routes,
        "_fetch_rows_with_limit",
        AsyncMock(return_value=[
            (account_a, "item-1"),
            (account_a, "item-2"),
            (account_a, "item-3"),
            (account_b, "item-4"),
        ]),
    )
    monkeypatch.setattr(
        jobs_routes,
        "MetadataLibraryService",
        lambda db_session: SimpleNamespace(ensure_active_images_category=AsyncMock(return_value=image_category)),
    )
    monkeypatch.setattr(
        jobs_routes,
        "_filter_unmapped_image_items",
        AsyncMock(return_value={
            account_a: ["item-1", "item-2", "item-3"],
            account_b: ["item-4"],
        }),
    )
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", enqueue_mock)

    response = await jobs_routes.create_analyze_library_image_assets_job(
        JobAnalyzeLibraryImageAssetsRequest(chunk_size=2, reprocess=False),
        db=object(),
    )

    assert response.total_items == 4
    assert response.total_jobs == 3
    assert len(response.job_ids) == 3
    first_payload = enqueue_mock.await_args_list[0].kwargs["payload"]
    assert first_payload["use_indexed_items"] is True
    assert first_payload["reprocess"] is False


@pytest.mark.asyncio
async def test_create_reindex_and_library_chunk_routes(monkeypatch):
    account_id = uuid4()
    enqueue_mock = AsyncMock(side_effect=[
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    ])
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", enqueue_mock)
    monkeypatch.setattr(
        jobs_routes,
        "_fetch_rows_with_limit",
        AsyncMock(return_value=[
            (account_id, "item-1"),
            (account_id, "item-2"),
            (account_id, "item-3"),
        ]),
    )
    monkeypatch.setattr(
        jobs_routes,
        "_filter_unmapped_comic_items",
        AsyncMock(return_value={account_id: ["item-1", "item-2", "item-3"]}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await jobs_routes.create_reindex_comic_covers_job(
            JobReindexComicCoversRequest(plugin_key="wrong"),
            job_service=SimpleNamespace(session=object()),
        )

    assert exc_info.value.status_code == 404

    reindex_job = await jobs_routes.create_reindex_comic_covers_job(
        JobReindexComicCoversRequest(plugin_key=jobs_routes.COMICS_LIBRARY_KEY),
        job_service=SimpleNamespace(session=object()),
    )
    extract_response = await jobs_routes.create_extract_library_comic_assets_job(
        JobExtractLibraryComicAssetsRequest(chunk_size=2),
        db=object(),
    )

    assert reindex_job.id
    assert extract_response.total_items == 3
    assert extract_response.total_jobs == 2


@pytest.mark.asyncio
async def test_create_map_library_books_and_extract_library_delegate(monkeypatch):
    account_id = uuid4()
    enqueue_mock = AsyncMock(side_effect=[
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    ])
    monkeypatch.setattr(jobs_routes, "enqueue_job_command", enqueue_mock)
    monkeypatch.setattr(
        jobs_routes,
        "MetadataLibraryService",
        lambda db_session: SimpleNamespace(
            get_active_books_category=AsyncMock(return_value=SimpleNamespace(plugin_key=jobs_routes.BOOKS_LIBRARY_KEY))
        ),
    )
    monkeypatch.setattr(
        jobs_routes,
        "_fetch_rows_with_limit",
        AsyncMock(return_value=[
            (account_id, "book-1"),
            (account_id, "book-2"),
            (account_id, "book-3"),
        ]),
    )
    monkeypatch.setattr(
        jobs_routes,
        "_filter_unmapped_book_items",
        AsyncMock(return_value={account_id: ["book-1", "book-2", "book-3"]}),
    )

    response = await jobs_routes.create_map_library_books_job(
        JobMapLibraryBooksRequest(chunk_size=2),
        db=object(),
    )

    assert response.total_items == 3
    assert response.total_jobs == 2
    assert enqueue_mock.await_args_list[0].kwargs["dedupe_key"] == f"books-map:{account_id}:0:2"
    assert enqueue_mock.await_args_list[1].kwargs["dedupe_key"] == f"books-map:{account_id}:2:2"

    delegate_mock = AsyncMock(return_value=SimpleNamespace(
        total_items=5,
        total_jobs=2,
        chunk_size=250,
        job_ids=[uuid4(), uuid4()],
    ))
    monkeypatch.setattr(jobs_routes, "create_map_library_books_job", delegate_mock)

    delegated = await jobs_routes.create_extract_library_book_assets_job(
        JobExtractLibraryBookAssetsRequest(chunk_size=250),
        db=object(),
    )

    assert delegated.total_items == 5
    assert delegated.total_jobs == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "service", "expected"),
    [
        (
            lambda job_id, svc: jobs_routes.delete_job(job_id, svc),
            lambda: SimpleNamespace(delete_job=AsyncMock(return_value=None)),
            None,
        ),
        (
            lambda job_id, svc: jobs_routes.cancel_job(job_id, svc),
            lambda: SimpleNamespace(request_cancel=AsyncMock(return_value="job")),
            "job",
        ),
        (
            lambda job_id, svc: jobs_routes.reprocess_job(job_id, svc),
            lambda: SimpleNamespace(reprocess_job=AsyncMock(return_value="job")),
            "job",
        ),
        (
            lambda job_id, svc: jobs_routes.list_job_attempts(job_id, svc, limit=5),
            lambda: SimpleNamespace(get_job_attempts=AsyncMock(return_value=["attempt-1"])),
            ["attempt-1"],
        ),
    ],
)
async def test_terminal_job_routes_return_service_results(func, service, expected):
    result = await func(uuid4(), service())
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "service"),
    [
        (
            lambda job_id, svc: jobs_routes.delete_job(job_id, svc),
            lambda: SimpleNamespace(delete_job=AsyncMock(side_effect=NotFoundError("missing"))),
        ),
        (
            lambda job_id, svc: jobs_routes.cancel_job(job_id, svc),
            lambda: SimpleNamespace(request_cancel=AsyncMock(side_effect=DomainError("invalid"))),
        ),
        (
            lambda job_id, svc: jobs_routes.reprocess_job(job_id, svc),
            lambda: SimpleNamespace(reprocess_job=AsyncMock(side_effect=DomainError("invalid"))),
        ),
        (
            lambda job_id, svc: jobs_routes.list_job_attempts(job_id, svc, limit=5),
            lambda: SimpleNamespace(get_job_attempts=AsyncMock(side_effect=NotFoundError("missing"))),
        ),
    ],
)
async def test_terminal_job_routes_map_domain_errors(func, service):
    with pytest.raises(HTTPException) as exc_info:
        await func(uuid4(), service())

    assert exc_info.value.status_code in {400, 404}
