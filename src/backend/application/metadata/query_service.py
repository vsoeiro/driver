"""Query services for item listing and metadata series aggregation."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Float, String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.common.metadata_filters import build_metadata_filter_conditions
from backend.db.models import Item, ItemMetadata, MetadataCategory
from backend.domain.errors import NotFoundError
from backend.schemas.items import ItemListResponse, SimilarItemsReportResponse
from backend.schemas.metadata import SeriesSummaryResponse


def _parse_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = int(float(text))
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _stem_name(name: str, extension: str | None) -> str:
    clean_name = name.strip()
    clean_ext = (extension or "").strip().lstrip(".")
    if not clean_ext:
        return clean_name
    suffix = f".{clean_ext}"
    if clean_name.lower().endswith(suffix.lower()):
        return clean_name[: -len(suffix)]
    return clean_name


LOW_PRIORITY_PATH_MARKERS = (
    "/venv/",
    "/.venv/",
    "/env/",
    "/site-packages/",
    "/__pycache__/",
    "/node_modules/",
    "/.objects/",
    "/__covers__/",
)


def _is_low_priority_path(path: str | None) -> tuple[bool, str | None]:
    normalized = _normalize_text(path)
    for marker in LOW_PRIORITY_PATH_MARKERS:
        if marker in normalized:
            return True, marker.strip("/")
    return False, None


class MetadataQueryService:
    """Read-only query service used by items + metadata APIs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_similar_items_report(
        self,
        *,
        page: int,
        page_size: int,
        account_id: UUID | None,
        scope: str,
        sort_by: str,
        sort_order: str,
        extensions: list[str] | None,
        hide_low_priority: bool,
    ) -> SimilarItemsReportResponse:
        stmt = select(
            Item.account_id,
            Item.item_id,
            Item.name,
            Item.path,
            Item.extension,
            Item.size,
            Item.modified_at,
        ).where(Item.item_type == "file")
        if account_id:
            stmt = stmt.where(Item.account_id == account_id)

        ext_filter_set = {
            _normalize_text(ext).lstrip(".")
            for ext in (extensions or [])
            if _normalize_text(ext).lstrip(".")
        }

        result = await self.session.execute(stmt)
        rows = result.all()

        with_extension_groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
        without_extension_groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

        dedupe_map: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
        raw_records = 0
        for row in rows:
            raw_records += 1
            normalized_extension = _normalize_text(row.extension).lstrip(".")
            normalized_path = _normalize_text(row.path)
            dedupe_key = (
                str(row.account_id),
                normalized_path,
                _normalize_text(row.name),
                int(row.size or 0),
                normalized_extension,
            )
            current_modified = row.modified_at
            existing = dedupe_map.get(dedupe_key)
            if existing is not None:
                existing_modified = existing.get("modified_at")
                should_replace = (
                    existing_modified is None
                    or (current_modified is not None and current_modified > existing_modified)
                )
                if should_replace:
                    existing["item_id"] = row.item_id
                    existing["modified_at"] = current_modified
                existing["source_records"] = int(existing.get("source_records") or 1) + 1
                continue

            entry = {
                "account_id": row.account_id,
                "item_id": row.item_id,
                "name": row.name,
                "path": row.path,
                "extension": row.extension,
                "size": int(row.size or 0),
                "modified_at": row.modified_at,
                "source_records": 1,
            }
            dedupe_map[dedupe_key] = entry

        entries = list(dedupe_map.values())

        for entry in entries:
            normalized_name = _normalize_text(entry["name"])
            normalized_extension = _normalize_text(entry["extension"]).lstrip(".")
            if ext_filter_set and normalized_extension not in ext_filter_set:
                continue
            with_key = (normalized_name, int(entry["size"] or 0), normalized_extension)
            with_extension_groups[with_key].append(entry)

            stem = _normalize_text(_stem_name(entry["name"], entry["extension"]))
            without_key = (stem, int(entry["size"] or 0))
            without_extension_groups[without_key].append(entry)

        groups: list[dict[str, Any]] = []

        def should_include_group(items: list[dict[str, Any]]) -> tuple[bool, bool]:
            account_counts = defaultdict(int)
            for item in items:
                account_counts[item["account_id"]] += 1
            has_same_account_matches = any(count > 1 for count in account_counts.values())
            has_cross_account_matches = len(account_counts) > 1
            if scope == "same_account" and not has_same_account_matches:
                return False, False
            if scope == "cross_account" and not has_cross_account_matches:
                return False, False
            return has_same_account_matches, has_cross_account_matches

        for (normalized_name, size, normalized_extension), items in with_extension_groups.items():
            if len(items) < 2:
                continue
            has_same_account_matches, has_cross_account_matches = should_include_group(items)
            if not has_same_account_matches and not has_cross_account_matches and scope in ("same_account", "cross_account"):
                continue
            extension_values = sorted({_normalize_text(item["extension"]).lstrip(".") for item in items if item["extension"]})
            low_markers = sorted(
                {reason for reason in (_is_low_priority_path(item.get("path"))[1] for item in items) if reason}
            )
            low_hits = sum(1 for item in items if _is_low_priority_path(item.get("path"))[0])
            is_low_priority = low_hits == len(items)
            groups.append(
                {
                    "match_type": "with_extension",
                    "name": normalized_name,
                    "size": size,
                    "extension": normalized_extension or None,
                    "extensions": extension_values,
                    "total_items": len(items),
                    "total_accounts": len({item["account_id"] for item in items}),
                    "has_same_account_matches": has_same_account_matches,
                    "has_cross_account_matches": has_cross_account_matches,
                    "deletable_items": max(0, len(items) - 1),
                    "potential_savings_bytes": max(0, len(items) - 1) * int(size or 0),
                    "priority_level": "low" if is_low_priority else "normal",
                    "low_priority_reasons": low_markers if is_low_priority else [],
                    "items": sorted(items, key=lambda item: (str(item["account_id"]), item["name"], item["path"] or "")),
                }
            )

        for (stem, size), items in without_extension_groups.items():
            if len(items) < 2:
                continue
            extension_values = sorted({_normalize_text(item["extension"]).lstrip(".") for item in items})
            has_blank_extension = any(not ext for ext in extension_values)
            has_extension_variation = len(extension_values) > 1
            if not has_blank_extension and not has_extension_variation:
                continue
            has_same_account_matches, has_cross_account_matches = should_include_group(items)
            if not has_same_account_matches and not has_cross_account_matches and scope in ("same_account", "cross_account"):
                continue
            low_markers = sorted(
                {reason for reason in (_is_low_priority_path(item.get("path"))[1] for item in items) if reason}
            )
            low_hits = sum(1 for item in items if _is_low_priority_path(item.get("path"))[0])
            is_low_priority = low_hits == len(items)
            groups.append(
                {
                    "match_type": "without_extension",
                    "name": stem,
                    "size": size,
                    "extension": None,
                    "extensions": [ext for ext in extension_values if ext],
                    "total_items": len(items),
                    "total_accounts": len({item["account_id"] for item in items}),
                    "has_same_account_matches": has_same_account_matches,
                    "has_cross_account_matches": has_cross_account_matches,
                    "deletable_items": max(0, len(items) - 1),
                    "potential_savings_bytes": max(0, len(items) - 1) * int(size or 0),
                    "priority_level": "low" if is_low_priority else "normal",
                    "low_priority_reasons": low_markers if is_low_priority else [],
                    "items": sorted(items, key=lambda item: (str(item["account_id"]), item["name"], item["path"] or "")),
                }
            )

        if hide_low_priority:
            groups = [group for group in groups if group.get("priority_level") != "low"]

        if sort_by == "name":
            groups.sort(
                key=lambda group: (
                    1 if group.get("priority_level") == "low" else 0,
                    group["name"],
                    group["match_type"],
                ),
                reverse=(sort_order == "desc"),
            )
        elif sort_by == "size":
            groups.sort(
                key=lambda group: (
                    1 if group.get("priority_level") == "low" else 0,
                    group["size"],
                    group["name"],
                    group["match_type"],
                ),
                reverse=(sort_order == "desc"),
            )
        else:
            groups.sort(
                key=lambda group: (
                    1 if group.get("priority_level") == "low" else 0,
                    -group["total_items"],
                    -group["size"],
                    group["name"],
                    group["match_type"],
                )
            )

        total_groups = len(groups)
        total_items = sum(group["total_items"] for group in groups)
        collapsed_records = max(0, raw_records - len(entries))
        potential_savings_bytes = sum(int(group["potential_savings_bytes"] or 0) for group in groups)
        start = (page - 1) * page_size
        end = start + page_size
        paged_groups = groups[start:end]
        total_pages = (total_groups + page_size - 1) // page_size if total_groups > 0 else 0

        return SimilarItemsReportResponse(
            generated_at=datetime.now(UTC),
            total_groups=total_groups,
            total_items=total_items,
            collapsed_records=collapsed_records,
            potential_savings_bytes=potential_savings_bytes,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            groups=paged_groups,
        )

    async def list_items(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str,
        sort_order: str,
        metadata_sort_attribute_id: str | None,
        metadata_sort_data_type: str | None,
        q: str | None,
        search_fields: str,
        path_prefix: str | None,
        direct_children_only: bool,
        extensions: list[str] | None,
        item_type: str | None,
        size_min: int | None,
        size_max: int | None,
        account_id: UUID | None,
        category_id: UUID | None,
        has_metadata: bool | None,
        metadata_filters: str | None,
        include_total: bool,
    ) -> ItemListResponse:
        query = select(Item, ItemMetadata, MetadataCategory.name.label("category_name")).outerjoin(
            ItemMetadata,
            (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id),
        ).outerjoin(
            MetadataCategory,
            ItemMetadata.category_id == MetadataCategory.id,
        )

        if account_id:
            query = query.where(Item.account_id == account_id)

        if q:
            search_pattern = f"%{q}%"
            if search_fields == "name":
                query = query.where(Item.name.ilike(search_pattern))
            elif search_fields == "path":
                query = query.where(Item.path.ilike(search_pattern))
            else:
                query = query.where(
                    Item.name.ilike(search_pattern) | Item.path.ilike(search_pattern)
                )

        if path_prefix:
            clean_prefix = path_prefix.rstrip("/")
            if direct_children_only:
                child_pattern = clean_prefix + "/%"
                grandchild_pattern = clean_prefix + "/%/%"
                query = query.where(
                    Item.path.ilike(child_pattern),
                    ~Item.path.ilike(grandchild_pattern),
                )
            else:
                child_pattern = clean_prefix + "/%"
                query = query.where(Item.path.ilike(child_pattern))

        if extensions:
            clean_exts = [e.lstrip(".").lower() for e in extensions]
            query = query.where(Item.extension.in_(clean_exts))

        if item_type:
            query = query.where(Item.item_type == item_type)

        if size_min is not None:
            query = query.where(Item.size >= size_min)

        if size_max is not None:
            query = query.where(Item.size <= size_max)

        if category_id:
            query = query.where(ItemMetadata.category_id == category_id)

        if has_metadata is True:
            query = query.where(ItemMetadata.id.isnot(None))
        elif has_metadata is False:
            query = query.where(ItemMetadata.id.is_(None))

        metadata_conditions: list[Any] = []
        if metadata_filters:
            try:
                parsed_filters = json.loads(metadata_filters)
                metadata_conditions = build_metadata_filter_conditions(parsed_filters, ItemMetadata.values)
            except Exception:
                metadata_conditions = []

        for condition in metadata_conditions:
            query = query.where(condition)

        total: int | None = None
        if include_total:
            count_query = select(func.count(Item.id))

            if account_id:
                count_query = count_query.where(Item.account_id == account_id)
            if q:
                search_pattern = f"%{q}%"
                if search_fields == "name":
                    count_query = count_query.where(Item.name.ilike(search_pattern))
                elif search_fields == "path":
                    count_query = count_query.where(Item.path.ilike(search_pattern))
                else:
                    count_query = count_query.where(
                        Item.name.ilike(search_pattern) | Item.path.ilike(search_pattern)
                    )
            if path_prefix:
                clean_prefix = path_prefix.rstrip("/")
                if direct_children_only:
                    child_pattern = clean_prefix + "/%"
                    grandchild_pattern = clean_prefix + "/%/%"
                    count_query = count_query.where(
                        Item.path.ilike(child_pattern),
                        ~Item.path.ilike(grandchild_pattern),
                    )
                else:
                    child_pattern = clean_prefix + "/%"
                    count_query = count_query.where(Item.path.ilike(child_pattern))
            if extensions:
                clean_exts = [e.lstrip(".").lower() for e in extensions]
                count_query = count_query.where(Item.extension.in_(clean_exts))
            if item_type:
                count_query = count_query.where(Item.item_type == item_type)
            if size_min is not None:
                count_query = count_query.where(Item.size >= size_min)
            if size_max is not None:
                count_query = count_query.where(Item.size <= size_max)
            if category_id:
                count_query = count_query.join(
                    ItemMetadata,
                    (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id),
                ).where(ItemMetadata.category_id == category_id)
            if has_metadata is True:
                count_query = count_query.join(
                    ItemMetadata,
                    (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id),
                    isouter=False,
                ) if not category_id else count_query
            elif has_metadata is False:
                count_query = count_query.outerjoin(
                    ItemMetadata,
                    (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id),
                ).where(ItemMetadata.id.is_(None)) if not category_id else count_query

            if metadata_conditions:
                if not category_id and has_metadata is None:
                    count_query = count_query.join(
                        ItemMetadata,
                        (Item.item_id == ItemMetadata.item_id) & (Item.account_id == ItemMetadata.account_id),
                    )
                for condition in metadata_conditions:
                    count_query = count_query.where(condition)

            total = (await self.session.execute(count_query)).scalar_one()

        sort_expression = getattr(Item, sort_by)
        if metadata_sort_attribute_id:
            metadata_field_text = func.coalesce(
                ItemMetadata.values[metadata_sort_attribute_id].as_string(),
                cast(ItemMetadata.values[metadata_sort_attribute_id], String),
            )
            if metadata_sort_data_type == "number":
                numeric_text = func.nullif(
                    func.regexp_replace(metadata_field_text, r"[^0-9.\-]+", "", "g"),
                    "",
                )
                sort_expression = cast(numeric_text, Float)
            else:
                sort_expression = metadata_field_text

        primary_sort = sort_expression.desc().nullslast() if sort_order == "desc" else sort_expression.asc().nullslast()
        secondary_sort = Item.modified_at.desc().nullslast() if sort_order == "desc" else Item.modified_at.asc().nullslast()
        tie_breaker = Item.id.desc() if sort_order == "desc" else Item.id.asc()
        query = query.order_by(primary_sort, secondary_sort, tie_breaker)

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        rows = result.all()

        items = []
        for row in rows:
            item, metadata, category_name = row

            metadata_data = None
            if metadata:
                metadata_data = {
                    "id": str(metadata.id),
                    "account_id": metadata.account_id,
                    "item_id": metadata.item_id,
                    "category_id": metadata.category_id,
                    "values": metadata.values,
                    "version": metadata.version,
                    "updated_at": metadata.updated_at,
                    "category_name": category_name,
                }

            item_data = {
                "id": str(item.id),
                "account_id": item.account_id,
                "item_id": item.item_id,
                "parent_id": item.parent_id,
                "name": item.name,
                "path": item.path,
                "item_type": item.item_type,
                "mime_type": item.mime_type,
                "extension": item.extension,
                "size": item.size,
                "created_at": item.created_at,
                "modified_at": item.modified_at,
                "last_synced_at": item.last_synced_at,
                "web_url": None,
                "download_url": None,
                "metadata": metadata_data,
            }
            items.append(item_data)

        if total is None:
            total = ((page - 1) * page_size) + len(items)

        return ItemListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    async def get_category_series_summary(
        self,
        *,
        category_id: UUID,
        page: int,
        page_size: int,
        sort_by: str,
        sort_order: str,
        q: str | None,
        search_fields: str,
        account_id: UUID | None,
        item_type: str | None,
        metadata_filters: str | None,
    ) -> SeriesSummaryResponse:
        category_query = (
            select(MetadataCategory)
            .where(MetadataCategory.id == category_id)
            .options(selectinload(MetadataCategory.attributes))
        )
        category_result = await self.session.execute(category_query)
        category = category_result.scalar_one_or_none()
        if not category:
            raise NotFoundError("Category not found")

        attr_by_plugin_key = {
            (attr.plugin_field_key or "").strip().lower(): str(attr.id)
            for attr in category.attributes
            if attr.plugin_field_key
        }
        attr_by_name = {
            (attr.name or "").strip().lower(): str(attr.id)
            for attr in category.attributes
            if attr.name
        }

        series_attr_id = attr_by_plugin_key.get("series") or attr_by_name.get("series")
        if not series_attr_id:
            return SeriesSummaryResponse(rows=[], total=0, page=page, page_size=page_size, total_pages=0)

        volume_attr_id = attr_by_plugin_key.get("volume") or attr_by_name.get("volume")
        issue_attr_id = attr_by_plugin_key.get("issue_number") or attr_by_name.get("issue number")
        max_volumes_attr_id = attr_by_plugin_key.get("max_volumes") or attr_by_name.get("max volumes")
        max_issues_attr_id = attr_by_plugin_key.get("max_issues") or attr_by_name.get("max issues")
        status_attr_id = attr_by_plugin_key.get("series_status") or attr_by_name.get("series status")

        series_text_expr = func.trim(ItemMetadata.values[series_attr_id].as_string())
        series_key_expr = func.lower(series_text_expr)
        conditions = [
            ItemMetadata.category_id == category_id,
            series_text_expr.isnot(None),
            series_text_expr != "",
            ItemMetadata.account_id == Item.account_id,
            ItemMetadata.item_id == Item.item_id,
        ]

        if account_id:
            conditions.append(Item.account_id == account_id)
        if item_type:
            conditions.append(Item.item_type == item_type)
        if q:
            search_pattern = f"%{q}%"
            if search_fields == "name":
                conditions.append(Item.name.ilike(search_pattern))
            elif search_fields == "path":
                conditions.append(Item.path.ilike(search_pattern))
            else:
                conditions.append(Item.name.ilike(search_pattern) | Item.path.ilike(search_pattern))

        if metadata_filters:
            try:
                parsed_filters = json.loads(metadata_filters)
                conditions.extend(build_metadata_filter_conditions(parsed_filters, ItemMetadata.values))
            except Exception:
                pass

        count_stmt = (
            select(func.count(func.distinct(series_key_expr)))
            .select_from(ItemMetadata, Item)
            .where(*conditions)
        )
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        if total == 0:
            return SeriesSummaryResponse(rows=[], total=0, page=page, page_size=page_size, total_pages=0)

        series_name_agg = func.min(series_text_expr)
        total_items_agg = func.count(ItemMetadata.id)
        series_rows_stmt = (
            select(
                series_key_expr.label("series_key"),
                series_name_agg.label("series_name"),
                total_items_agg.label("total_items"),
            )
            .select_from(ItemMetadata, Item)
            .where(*conditions)
            .group_by(series_key_expr)
        )
        if sort_by == "total_items":
            series_rows_stmt = series_rows_stmt.order_by(
                total_items_agg.desc() if sort_order == "desc" else total_items_agg.asc(),
                series_name_agg.asc(),
            )
        else:
            series_rows_stmt = series_rows_stmt.order_by(
                series_name_agg.desc() if sort_order == "desc" else series_name_agg.asc()
            )

        series_rows_stmt = series_rows_stmt.offset((page - 1) * page_size).limit(page_size)
        series_rows_result = await self.session.execute(series_rows_stmt)
        series_rows = series_rows_result.all()
        if not series_rows:
            return SeriesSummaryResponse(rows=[], total=total, page=page, page_size=page_size, total_pages=total_pages)

        page_series_keys = [row.series_key for row in series_rows]
        by_key = {
            row.series_key: {
                "series_name": (row.series_name or "").strip() or "Unknown",
                "total_items": int(row.total_items or 0),
                "owned_volumes": set(),
                "issues_by_volume": {},
                "max_volumes_candidates": [],
                "max_issues_candidates": [],
                "status_votes": {},
            }
            for row in series_rows
        }

        if volume_attr_id:
            volume_expr = func.trim(ItemMetadata.values[volume_attr_id].as_string())
            volume_stmt = (
                select(series_key_expr.label("series_key"), volume_expr.label("volume_text"))
                .select_from(ItemMetadata, Item)
                .where(*conditions, series_key_expr.in_(page_series_keys), volume_expr.isnot(None), volume_expr != "")
                .group_by(series_key_expr, volume_expr)
            )
            for row in (await self.session.execute(volume_stmt)).all():
                parsed_volume = _parse_positive_int(row.volume_text)
                if parsed_volume:
                    by_key[row.series_key]["owned_volumes"].add(parsed_volume)

        if volume_attr_id and issue_attr_id:
            volume_expr = func.trim(ItemMetadata.values[volume_attr_id].as_string())
            issue_expr = func.trim(ItemMetadata.values[issue_attr_id].as_string())
            issue_stmt = (
                select(
                    series_key_expr.label("series_key"),
                    volume_expr.label("volume_text"),
                    issue_expr.label("issue_text"),
                )
                .select_from(ItemMetadata, Item)
                .where(
                    *conditions,
                    series_key_expr.in_(page_series_keys),
                    volume_expr.isnot(None),
                    volume_expr != "",
                    issue_expr.isnot(None),
                    issue_expr != "",
                )
                .group_by(series_key_expr, volume_expr, issue_expr)
            )
            for row in (await self.session.execute(issue_stmt)).all():
                parsed_volume = _parse_positive_int(row.volume_text)
                parsed_issue = _parse_positive_int(row.issue_text)
                if not parsed_volume or not parsed_issue:
                    continue
                volume_bucket = by_key[row.series_key]["issues_by_volume"].setdefault(parsed_volume, set())
                volume_bucket.add(parsed_issue)

        if max_volumes_attr_id:
            max_volumes_expr = func.trim(ItemMetadata.values[max_volumes_attr_id].as_string())
            max_volumes_stmt = (
                select(series_key_expr.label("series_key"), max_volumes_expr.label("max_volumes_text"))
                .select_from(ItemMetadata, Item)
                .where(
                    *conditions,
                    series_key_expr.in_(page_series_keys),
                    max_volumes_expr.isnot(None),
                    max_volumes_expr != "",
                )
                .group_by(series_key_expr, max_volumes_expr)
            )
            for row in (await self.session.execute(max_volumes_stmt)).all():
                parsed_value = _parse_positive_int(row.max_volumes_text)
                if parsed_value:
                    by_key[row.series_key]["max_volumes_candidates"].append(parsed_value)

        if max_issues_attr_id:
            max_issues_expr = func.trim(ItemMetadata.values[max_issues_attr_id].as_string())
            max_issues_stmt = (
                select(series_key_expr.label("series_key"), max_issues_expr.label("max_issues_text"))
                .select_from(ItemMetadata, Item)
                .where(
                    *conditions,
                    series_key_expr.in_(page_series_keys),
                    max_issues_expr.isnot(None),
                    max_issues_expr != "",
                )
                .group_by(series_key_expr, max_issues_expr)
            )
            for row in (await self.session.execute(max_issues_stmt)).all():
                parsed_value = _parse_positive_int(row.max_issues_text)
                if parsed_value:
                    by_key[row.series_key]["max_issues_candidates"].append(parsed_value)

        if status_attr_id:
            status_expr = func.lower(func.trim(ItemMetadata.values[status_attr_id].as_string()))
            status_stmt = (
                select(
                    series_key_expr.label("series_key"),
                    status_expr.label("series_status"),
                    func.count(ItemMetadata.id).label("status_count"),
                )
                .select_from(ItemMetadata, Item)
                .where(
                    *conditions,
                    series_key_expr.in_(page_series_keys),
                    status_expr.isnot(None),
                    status_expr != "",
                )
                .group_by(series_key_expr, status_expr)
            )
            for row in (await self.session.execute(status_stmt)).all():
                by_key[row.series_key]["status_votes"][row.series_status] = int(row.status_count or 0)

        rows = []
        for series_key in page_series_keys:
            row = by_key.get(series_key)
            if not row:
                continue

            owned_volumes = sorted(row["owned_volumes"])
            owned_volume_max = max(owned_volumes) if owned_volumes else 0
            declared_max_volumes = max(row["max_volumes_candidates"]) if row["max_volumes_candidates"] else 0
            max_volumes = max(owned_volume_max, declared_max_volumes)
            max_issues = max(row["max_issues_candidates"]) if row["max_issues_candidates"] else 0

            status_votes = row["status_votes"]
            if status_votes:
                series_status = max(status_votes.items(), key=lambda item: item[1])[0]
            else:
                series_status = "unknown"

            issues_by_volume = {
                str(volume): sorted(issue_set)
                for volume, issue_set in row["issues_by_volume"].items()
            }
            rows.append(
                {
                    "series_name": row["series_name"],
                    "total_items": row["total_items"],
                    "owned_volumes": owned_volumes,
                    "issues_by_volume": issues_by_volume,
                    "max_volumes": max_volumes,
                    "max_issues": max_issues,
                    "series_status": series_status,
                }
            )

        return SeriesSummaryResponse(
            rows=rows,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
