from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.jobs.commands import enqueue_job_command
from backend.application.metadata.item_query_service import ItemQueryService
from backend.application.metadata.rules_service import MetadataRulesService
from backend.core.exceptions import DriveOrganizerError
from backend.db.models import Item, ItemMetadata, LinkedAccount, MetadataCategory
from backend.schemas.metadata import MetadataRuleCreate
from backend.security.token_manager import TokenManager
from backend.services.jobs import JobService
from backend.services.metadata_versioning import apply_metadata_change
from backend.services.providers.factory import build_drive_client


@dataclass(slots=True)
class ToolDefinition:
    name: str
    permission: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]


def _parse_optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return UUID(text)
    except (TypeError, ValueError, AttributeError):
        return None


async def _resolve_read_account_uuid(session: AsyncSession, raw_value: Any) -> UUID | None:
    """Resolve account filters for read tools.

    Accepts:
    - UUID string
    - provider alias (e.g. "google", "microsoft", "dropbox")
    - partial email/display name/provider_account_id
    """
    if raw_value is None:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None

    parsed = _parse_optional_uuid(raw)
    if parsed is not None:
        return parsed

    lowered = raw.lower()
    rows = (await session.execute(select(LinkedAccount))).scalars().all()
    matches = []
    for account in rows:
        provider = str(account.provider or "").lower()
        email = str(account.email or "").lower()
        display_name = str(account.display_name or "").lower()
        provider_account_id = str(account.provider_account_id or "").lower()
        if (
            lowered == provider
            or lowered in email
            or lowered in display_name
            or lowered == provider_account_id
        ):
            matches.append(account)

    if len(matches) == 1:
        return matches[0].id

    if len(matches) > 1:
        labels = [f"{item.provider}:{item.email}" for item in matches[:5]]
        raise DriveOrganizerError(
            "Conta ambigua para filtro account_id. Seja especifico usando email ou UUID. "
            f"Candidatas: {', '.join(labels)}",
            status_code=400,
        )

    raise DriveOrganizerError(
        "Conta nao encontrada para filtro account_id. Use UUID valido, email ou provider existente.",
        status_code=400,
    )


async def _tool_items_count_by_name(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("q") or "").strip()
    if not query:
        raise DriveOrganizerError("'q' is required for items.count_by_name", status_code=400)
    service = ItemQueryService(session)
    response = await service.list_items(
        page=1,
        page_size=1,
        sort_by="modified_at",
        sort_order="desc",
        metadata_sort_attribute_id=None,
        metadata_sort_data_type=None,
        q=query,
        search_fields="name",
        path_prefix=None,
        direct_children_only=False,
        extensions=None,
        item_type=None,
        size_min=None,
        size_max=None,
        account_id=None,
        category_id=None,
        has_metadata=None,
        metadata_filters=None,
        include_total=True,
    )
    return {"query": query, "total": int(response.total)}


async def _tool_items_count(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    service = ItemQueryService(session)
    q_value = (str(args.get("q")) if args.get("q") else None)
    search_fields = str(args.get("search_fields") or "both")
    path_contains = str(args.get("path_contains") or "").strip()
    account_hint = args.get("account_id")
    if not account_hint and search_fields.strip().lower() == "account_id":
        account_hint = q_value or path_contains
    resolved_account_id = await _resolve_read_account_uuid(session, account_hint)
    if resolved_account_id is not None:
        q_value = None
        path_contains = ""
        search_fields = "both"
    if path_contains and not q_value:
        q_value = path_contains
        search_fields = "path"
    response = await service.list_items(
        page=1,
        page_size=1,
        sort_by="modified_at",
        sort_order="desc",
        metadata_sort_attribute_id=None,
        metadata_sort_data_type=None,
        q=q_value,
        search_fields=search_fields,
        path_prefix=(str(args.get("path_prefix")) if args.get("path_prefix") else None),
        direct_children_only=bool(args.get("direct_children_only") or False),
        extensions=args.get("extensions") if isinstance(args.get("extensions"), list) else None,
        item_type=(str(args.get("item_type")) if args.get("item_type") else None),
        size_min=int(args.get("size_min")) if args.get("size_min") is not None else None,
        size_max=int(args.get("size_max")) if args.get("size_max") is not None else None,
        account_id=resolved_account_id,
        category_id=_parse_optional_uuid(args.get("category_id")),
        has_metadata=args.get("has_metadata") if isinstance(args.get("has_metadata"), bool) else None,
        metadata_filters=args.get("metadata") if isinstance(args.get("metadata"), str) else None,
        include_total=True,
    )
    return {
        "total": int(response.total),
        "filters": {
            "q": args.get("q"),
            "search_fields": search_fields,
            "path_prefix": args.get("path_prefix"),
            "path_contains": path_contains or None,
            "item_type": args.get("item_type"),
            "account_id": str(resolved_account_id) if resolved_account_id else None,
            "category_id": args.get("category_id"),
        },
    }


async def _tool_items_search(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    service = ItemQueryService(session)
    page = max(1, int(args.get("page") or 1))
    page_size = min(100, max(1, int(args.get("page_size") or 20)))
    resolved_account_id = await _resolve_read_account_uuid(session, args.get("account_id"))
    response = await service.list_items(
        page=page,
        page_size=page_size,
        sort_by="modified_at",
        sort_order="desc",
        metadata_sort_attribute_id=None,
        metadata_sort_data_type=None,
        q=(str(args.get("q")) if args.get("q") else None),
        search_fields=str(args.get("search_fields") or "both"),
        path_prefix=(str(args.get("path_prefix")) if args.get("path_prefix") else None),
        direct_children_only=bool(args.get("direct_children_only") or False),
        extensions=args.get("extensions") if isinstance(args.get("extensions"), list) else None,
        item_type=(str(args.get("item_type")) if args.get("item_type") else None),
        size_min=int(args.get("size_min")) if args.get("size_min") is not None else None,
        size_max=int(args.get("size_max")) if args.get("size_max") is not None else None,
        account_id=resolved_account_id,
        category_id=_parse_optional_uuid(args.get("category_id")),
        has_metadata=args.get("has_metadata") if isinstance(args.get("has_metadata"), bool) else None,
        metadata_filters=args.get("metadata") if isinstance(args.get("metadata"), str) else None,
        include_total=True,
    )
    rows = [
        {
            "account_id": str(item.account_id),
            "item_id": item.item_id,
            "name": item.name,
            "path": item.path,
            "extension": item.extension,
            "size": int(item.size or 0),
            "modified_at": item.modified_at.isoformat() if item.modified_at else None,
        }
        for item in response.items
    ]
    return {
        "total": int(response.total),
        "page": response.page,
        "page_size": response.page_size,
        "items": rows,
    }


async def _tool_items_top_extensions(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    limit = min(50, max(1, int(args.get("limit") or 10)))
    stmt = (
        select(func.lower(func.coalesce(Item.extension, "")).label("ext"), func.count(Item.id).label("count"))
        .where(Item.item_type == "file")
        .group_by("ext")
        .order_by(func.count(Item.id).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "items": [
            {"extension": (row.ext or "(none)"), "count": int(row.count or 0)}
            for row in rows
        ]
    }


async def _tool_items_similar_report(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    service = ItemQueryService(session)
    resolved_account_id = await _resolve_read_account_uuid(session, args.get("account_id"))
    response = await service.get_similar_items_report(
        page=max(1, int(args.get("page") or 1)),
        page_size=min(100, max(1, int(args.get("page_size") or 20))),
        account_id=resolved_account_id,
        scope=str(args.get("scope") or "all"),
        sort_by=str(args.get("sort_by") or "relevance"),
        sort_order=str(args.get("sort_order") or "desc"),
        extensions=args.get("extensions") if isinstance(args.get("extensions"), list) else None,
        hide_low_priority=bool(args.get("hide_low_priority") or False),
    )
    return {
        "total_groups": int(response.total_groups),
        "total_items": int(response.total_items),
        "potential_savings_bytes": int(response.potential_savings_bytes),
        "groups": [group.model_dump(mode="json") for group in response.groups],
    }


async def _tool_jobs_status_overview(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    limit = min(500, max(1, int(args.get("limit") or 100)))
    job_service = JobService(session)
    jobs = await job_service.get_jobs(limit=limit, offset=0, include_estimates=False)
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for job in jobs:
        by_status[job.status] = by_status.get(job.status, 0) + 1
        by_type[job.type] = by_type.get(job.type, 0) + 1
    return {"sample_size": len(jobs), "by_status": by_status, "by_type": by_type}


async def _tool_accounts_list(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(LinkedAccount).order_by(LinkedAccount.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "accounts": [
            {
                "id": str(account.id),
                "provider": account.provider,
                "email": account.email,
                "display_name": account.display_name,
                "is_active": bool(account.is_active),
            }
            for account in rows
        ]
    }


async def _tool_accounts_resolve(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise DriveOrganizerError("'query' is required for accounts.resolve", status_code=400)
    lowered = query.lower()
    rows = (await session.execute(select(LinkedAccount).order_by(LinkedAccount.created_at.desc()))).scalars().all()
    matches = []
    for account in rows:
        provider = str(account.provider or "").lower()
        email = str(account.email or "").lower()
        display_name = str(account.display_name or "").lower()
        provider_account_id = str(account.provider_account_id or "").lower()
        if (
            lowered == provider
            or lowered in email
            or lowered in display_name
            or lowered == provider_account_id
        ):
            matches.append(
                {
                    "id": str(account.id),
                    "provider": account.provider,
                    "email": account.email,
                    "display_name": account.display_name,
                    "is_active": bool(account.is_active),
                }
            )
    return {"query": query, "total_matches": len(matches), "accounts": matches}


async def _tool_rules_create_from_structured_payload(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    payload = args.get("rule")
    if not isinstance(payload, dict):
        raise DriveOrganizerError("'rule' object is required", status_code=400)
    service = MetadataRulesService(session)
    created = await service.create_rule(MetadataRuleCreate.model_validate(payload))
    return {"rule_id": str(created.id), "name": created.name}


async def _tool_jobs_create_sync(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    account_id = args.get("account_id")
    if not account_id:
        raise DriveOrganizerError("'account_id' is required", status_code=400)
    job = await enqueue_job_command(
        session,
        job_type="sync_items",
        payload={"account_id": str(account_id)},
    )
    return {"job_id": str(job.id), "status": job.status, "type": job.type}


async def _tool_drive_move_or_rename(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    account_id = args.get("account_id")
    item_id = args.get("item_id")
    if not account_id or not item_id:
        raise DriveOrganizerError("'account_id' and 'item_id' are required", status_code=400)
    account = await session.get(LinkedAccount, UUID(str(account_id)))
    if not account:
        raise DriveOrganizerError("Account not found", status_code=404)

    client = build_drive_client(account, TokenManager(session))
    moved = await client.update_item(
        account,
        str(item_id),
        name=str(args.get("name")) if args.get("name") is not None else None,
        parent_id=str(args.get("parent_id")) if args.get("parent_id") is not None else None,
    )
    return {"item_id": moved.id, "name": moved.name, "web_url": moved.web_url}


async def _tool_metadata_batch_update(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    account_id = args.get("account_id")
    category_id = args.get("category_id")
    item_ids = args.get("item_ids")
    values = args.get("values")

    if not account_id or not category_id or not isinstance(item_ids, list) or not isinstance(values, dict):
        raise DriveOrganizerError(
            "'account_id', 'category_id', 'item_ids' and 'values' are required",
            status_code=400,
        )

    account_uuid = UUID(str(account_id))
    category_uuid = UUID(str(category_id))
    account = await session.get(LinkedAccount, account_uuid)
    if not account:
        raise DriveOrganizerError("Account not found", status_code=404)
    category = await session.get(MetadataCategory, category_uuid)
    if not category:
        raise DriveOrganizerError("Category not found", status_code=404)

    stmt = select(ItemMetadata).where(
        ItemMetadata.account_id == account_uuid,
        ItemMetadata.item_id.in_([str(item_id) for item_id in item_ids]),
    )
    result = await session.execute(stmt)
    existing_records = {record.item_id: record for record in result.scalars().all()}

    batch_id = uuid4()
    created = 0
    updated = 0
    for item_id in [str(item_id) for item_id in item_ids]:
        existing = existing_records.get(item_id)
        if existing and existing.category_id == category_uuid:
            merged_values = dict(existing.values or {})
            merged_values.update(values)
        else:
            merged_values = dict(values)
        change = await apply_metadata_change(
            session,
            account_id=account_uuid,
            item_id=item_id,
            category_id=category_uuid,
            values=merged_values,
            batch_id=batch_id,
        )
        if change["changed"]:
            if existing:
                updated += 1
            else:
                created += 1

    await session.commit()
    return {
        "batch_id": str(batch_id),
        "updated": updated,
        "created": created,
        "total": len(item_ids),
    }


def build_tool_registry() -> dict[str, ToolDefinition]:
    tools = [
        ToolDefinition(
            name="items.count",
            permission="read",
            description="Count items using optional filters (name/query/path/account/category/extensions)",
            input_schema={
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "search_fields": {"type": "string"},
                    "path_prefix": {"type": "string"},
                    "path_contains": {"type": "string"},
                    "direct_children_only": {"type": "boolean"},
                    "extensions": {"type": "array", "items": {"type": "string"}},
                    "item_type": {"type": "string"},
                    "size_min": {"type": "integer"},
                    "size_max": {"type": "integer"},
                    "account_id": {"type": "string"},
                    "category_id": {"type": "string"},
                    "has_metadata": {"type": "boolean"},
                    "metadata": {"type": "string"},
                },
            },
            handler=_tool_items_count,
        ),
        ToolDefinition(
            name="items.count_by_name",
            permission="read",
            description="Count items by name using indexed items query",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            handler=_tool_items_count_by_name,
        ),
        ToolDefinition(
            name="items.search",
            permission="read",
            description="Search items with filters and pagination",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}, "page": {"type": "integer"}, "page_size": {"type": "integer"}}},
            handler=_tool_items_search,
        ),
        ToolDefinition(
            name="items.top_extensions",
            permission="read",
            description="Return top file extensions in indexed library",
            input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
            handler=_tool_items_top_extensions,
        ),
        ToolDefinition(
            name="items.similar_report",
            permission="read",
            description="Return possible similar/duplicate files report",
            input_schema={"type": "object", "properties": {"page": {"type": "integer"}, "page_size": {"type": "integer"}}},
            handler=_tool_items_similar_report,
        ),
        ToolDefinition(
            name="jobs.status_overview",
            permission="read",
            description="Summarize recent jobs by status/type",
            input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
            handler=_tool_jobs_status_overview,
        ),
        ToolDefinition(
            name="accounts.list",
            permission="read",
            description="List linked accounts",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_accounts_list,
        ),
        ToolDefinition(
            name="accounts.resolve",
            permission="read",
            description="Resolve textual account hint to account candidates",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            handler=_tool_accounts_resolve,
        ),
        ToolDefinition(
            name="rules.create_from_structured_payload",
            permission="write",
            description="Create metadata rule from structured payload",
            input_schema={"type": "object", "properties": {"rule": {"type": "object"}}, "required": ["rule"]},
            handler=_tool_rules_create_from_structured_payload,
        ),
        ToolDefinition(
            name="jobs.create_sync",
            permission="write",
            description="Create sync_items background job",
            input_schema={"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]},
            handler=_tool_jobs_create_sync,
        ),
        ToolDefinition(
            name="drive.move_or_rename",
            permission="write",
            description="Move or rename one provider item",
            input_schema={"type": "object", "properties": {"account_id": {"type": "string"}, "item_id": {"type": "string"}, "name": {"type": "string"}, "parent_id": {"type": "string"}}, "required": ["account_id", "item_id"]},
            handler=_tool_drive_move_or_rename,
        ),
        ToolDefinition(
            name="metadata.batch_update",
            permission="write",
            description="Batch update metadata values for items",
            input_schema={"type": "object", "properties": {"account_id": {"type": "string"}, "category_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}}, "values": {"type": "object"}}, "required": ["account_id", "category_id", "item_ids", "values"]},
            handler=_tool_metadata_batch_update,
        ),
    ]
    return {tool.name: tool for tool in tools}


def catalog_entries(registry: dict[str, ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "permission": tool.permission,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in registry.values()
    ]


async def execute_tool(
    session: AsyncSession,
    *,
    registry: dict[str, ToolDefinition],
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    tool = registry.get(tool_name)
    if not tool:
        raise DriveOrganizerError(f"Unknown tool: {tool_name}", status_code=400)
    return await tool.handler(session, arguments)
