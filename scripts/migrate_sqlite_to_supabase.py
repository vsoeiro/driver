"""Migrate data from local SQLite to Supabase PostgreSQL.

Usage:
  uv run python scripts/migrate_sqlite_to_supabase.py \
    --sqlite-url sqlite:///./database.db \
    --postgres-url "postgresql+asyncpg://..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection, create_async_engine

EXCLUDED_TABLES = {"alembic_version", "sqlite_sequence"}


def _normalize_postgres_url(url: str) -> str:
    value = url.strip()
    if value.startswith("postgres://"):
        return "postgresql+asyncpg://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value[len("postgresql://") :]
    if value.startswith("postgresql+asyncpg://"):
        return value
    raise ValueError("Invalid Postgres URL. Expected postgres:// or postgresql://")


def _parse_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return value


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _convert_value(value: Any, column: sa.Column) -> Any:
    if value is None:
        return None

    col_type = column.type
    if isinstance(col_type, PG_UUID):
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            return uuid.UUID(value)
        raise ValueError(f"Invalid UUID value for column '{column.name}': {value!r}")

    if isinstance(col_type, (JSON, JSONB)):
        return _parse_json(value)

    if isinstance(col_type, sa.DateTime):
        return _parse_datetime(value)

    if isinstance(col_type, sa.Boolean):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}

    if isinstance(col_type, sa.Numeric):
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return Decimal(text)
            except InvalidOperation:
                return value

    return value


def _iter_source_rows(
    conn: sa.Connection,
    table: sa.Table,
    batch_size: int,
):
    result = conn.exec_driver_sql(f'SELECT * FROM "{table.name}"')
    keys = list(result.keys())
    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break
        yield [dict(zip(keys, row)) for row in rows]


def _load_source_id_set(conn: sa.Connection, table_name: str, id_column: str = "id") -> set[Any]:
    result = conn.exec_driver_sql(f'SELECT "{id_column}" FROM "{table_name}"')
    return {row[0] for row in result if row and row[0] is not None}


async def _truncate_tables(conn: AsyncConnection, tables: list[sa.Table]) -> None:
    if not tables:
        return
    names = ", ".join(f'"public"."{table.name}"' for table in tables)
    await conn.execute(sa.text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


async def migrate(
    *,
    sqlite_url: str,
    postgres_url: str,
    batch_size: int,
    truncate: bool,
    dry_run: bool,
) -> None:
    sqlite_engine = sa.create_engine(sqlite_url)
    sqlite_meta = sa.MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    pg_engine: AsyncEngine = create_async_engine(postgres_url)
    pg_meta = sa.MetaData()
    async with pg_engine.begin() as pg_conn:
        await pg_conn.run_sync(pg_meta.reflect, schema="public")

    sqlite_tables = {
        name: table
        for name, table in sqlite_meta.tables.items()
        if name not in EXCLUDED_TABLES
    }
    ordered_pg_tables = [
        table
        for table in pg_meta.sorted_tables
        if table.schema == "public" and table.name in sqlite_tables
    ]

    if not ordered_pg_tables:
        raise RuntimeError("No matching tables found between SQLite and PostgreSQL schemas.")

    print("Tables to migrate:")
    for table in ordered_pg_tables:
        print(f" - {table.name}")

    if dry_run:
        print("Dry-run enabled. No data will be written.")
        await pg_engine.dispose()
        sqlite_engine.dispose()
        return

    with sqlite_engine.connect() as sqlite_conn:
        async with pg_engine.begin() as pg_conn:
            if truncate:
                print("Truncating destination tables...")
                await _truncate_tables(pg_conn, ordered_pg_tables)

            for pg_table in ordered_pg_tables:
                src_table = sqlite_tables[pg_table.name]
                src_columns = set(src_table.columns.keys())
                dst_columns = [col for col in pg_table.columns if col.name in src_columns]
                if not dst_columns:
                    print(f"Skipping {pg_table.name}: no compatible columns")
                    continue

                total = 0
                skipped = 0
                valid_metadata_ids: set[Any] | None = None
                if pg_table.name == "item_metadata_history":
                    valid_metadata_ids = _load_source_id_set(sqlite_conn, "item_metadata")

                for src_batch in _iter_source_rows(sqlite_conn, src_table, batch_size):
                    converted_batch = []
                    for row in src_batch:
                        if valid_metadata_ids is not None and row.get("metadata_id") not in valid_metadata_ids:
                            skipped += 1
                            continue
                        converted = {}
                        for col in dst_columns:
                            converted[col.name] = _convert_value(row.get(col.name), col)
                        converted_batch.append(converted)

                    if converted_batch:
                        try:
                            await pg_conn.execute(pg_table.insert(), converted_batch)
                            total += len(converted_batch)
                        except IntegrityError:
                            # Fallback row-by-row so one bad record does not abort the whole table migration.
                            for converted in converted_batch:
                                try:
                                    await pg_conn.execute(pg_table.insert(), converted)
                                    total += 1
                                except IntegrityError:
                                    skipped += 1

                if skipped:
                    print(f"Migrated {total} rows -> {pg_table.name} (skipped {skipped} invalid rows)")
                else:
                    print(f"Migrated {total} rows -> {pg_table.name}")

    await pg_engine.dispose()
    sqlite_engine.dispose()
    print("Migration completed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite data to Supabase PostgreSQL.")
    parser.add_argument("--sqlite-url", default="sqlite:///./database.db", help="Source SQLite URL")
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("SUPABASE_DATABASE_URL", os.getenv("DATABASE_URL", "")),
        help="Destination Postgres URL",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Insert batch size")
    parser.add_argument("--no-truncate", action="store_true", help="Do not truncate destination tables first")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and exit")

    args = parser.parse_args()
    if not args.postgres_url:
        raise SystemExit("Missing --postgres-url (or SUPABASE_DATABASE_URL/DATABASE_URL env var).")

    postgres_url = _normalize_postgres_url(args.postgres_url)
    asyncio.run(
        migrate(
            sqlite_url=args.sqlite_url,
            postgres_url=postgres_url,
            batch_size=max(1, args.batch_size),
            truncate=not args.no_truncate,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
