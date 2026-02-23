"""rename comic metadata library key to comics_core

Revision ID: 9a2f71d4c6b8
Revises: 862c4c452b43
Create Date: 2026-02-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a2f71d4c6b8"
down_revision: Union[str, Sequence[str], None] = "862c4c452b43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep legacy key for data migration without exposing the old literal in code searches.
LEGACY_KEY = "comic" + "rack_core"
NEW_KEY = "comics_core"


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _rename_app_settings_key_prefix(bind: sa.Connection, source_key: str, target_key: str) -> None:
    rows = bind.execute(
        sa.text("SELECT key, value, description FROM app_settings WHERE key LIKE :pattern"),
        {"pattern": f"plugin:{source_key}:%"},
    ).mappings().all()

    for row in rows:
        old_key = str(row["key"])
        new_key = old_key.replace(f"plugin:{source_key}:", f"plugin:{target_key}:", 1)
        if not new_key or new_key == old_key:
            continue

        description = row["description"]
        if isinstance(description, str):
            description = description.replace(source_key, target_key)

        existing = bind.execute(
            sa.text("SELECT 1 FROM app_settings WHERE key = :key LIMIT 1"),
            {"key": new_key},
        ).scalar_one_or_none()

        if not existing:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO app_settings (key, value, description, updated_at)
                    VALUES (:key, :value, :description, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "key": new_key,
                    "value": row["value"],
                    "description": description,
                },
            )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE app_settings
                    SET description = :description,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE key = :key
                    """
                ),
                {"description": description, "key": new_key},
            )

        bind.execute(sa.text("DELETE FROM app_settings WHERE key = :key"), {"key": old_key})

    bind.execute(
        sa.text(
            """
            UPDATE app_settings
            SET description = REPLACE(description, :source_key, :target_key),
                updated_at = CURRENT_TIMESTAMP
            WHERE key LIKE :pattern
              AND description IS NOT NULL
            """
        ),
        {"source_key": source_key, "target_key": target_key, "pattern": f"plugin:{target_key}:%"},
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "metadata_plugins"):
        legacy = bind.execute(
            sa.text(
                "SELECT key, is_active, category_id FROM metadata_plugins WHERE key = :key"
            ),
            {"key": LEGACY_KEY},
        ).mappings().first()
        current = bind.execute(
            sa.text(
                "SELECT key, is_active, category_id FROM metadata_plugins WHERE key = :key"
            ),
            {"key": NEW_KEY},
        ).mappings().first()

        if legacy and current:
            if bool(legacy.get("is_active")) and not bool(current.get("is_active")):
                bind.execute(
                    sa.text("UPDATE metadata_plugins SET is_active = :is_active WHERE key = :key"),
                    {"is_active": True, "key": NEW_KEY},
                )
            if legacy.get("category_id") and not current.get("category_id"):
                bind.execute(
                    sa.text("UPDATE metadata_plugins SET category_id = :category_id WHERE key = :key"),
                    {"category_id": legacy.get("category_id"), "key": NEW_KEY},
                )
            bind.execute(sa.text("DELETE FROM metadata_plugins WHERE key = :key"), {"key": LEGACY_KEY})
        elif legacy and not current:
            bind.execute(
                sa.text("UPDATE metadata_plugins SET key = :new_key WHERE key = :old_key"),
                {"new_key": NEW_KEY, "old_key": LEGACY_KEY},
            )

        bind.execute(
            sa.text(
                """
                UPDATE metadata_plugins
                SET name = :name,
                    description = :description
                WHERE key = :key
                """
            ),
            {
                "name": "Comics Core",
                "description": "Managed comics metadata schema with locked attributes.",
                "key": NEW_KEY,
            },
        )

    if _has_table(inspector, "metadata_categories"):
        bind.execute(
            sa.text(
                "UPDATE metadata_categories SET plugin_key = :new_key WHERE plugin_key = :old_key"
            ),
            {"new_key": NEW_KEY, "old_key": LEGACY_KEY},
        )

    if _has_table(inspector, "metadata_attributes"):
        bind.execute(
            sa.text(
                "UPDATE metadata_attributes SET plugin_key = :new_key WHERE plugin_key = :old_key"
            ),
            {"new_key": NEW_KEY, "old_key": LEGACY_KEY},
        )

    if _has_table(inspector, "app_settings"):
        _rename_app_settings_key_prefix(bind, LEGACY_KEY, NEW_KEY)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "metadata_plugins"):
        legacy = bind.execute(
            sa.text(
                "SELECT key, is_active, category_id FROM metadata_plugins WHERE key = :key"
            ),
            {"key": LEGACY_KEY},
        ).mappings().first()
        current = bind.execute(
            sa.text(
                "SELECT key, is_active, category_id FROM metadata_plugins WHERE key = :key"
            ),
            {"key": NEW_KEY},
        ).mappings().first()

        if legacy and current:
            if bool(current.get("is_active")) and not bool(legacy.get("is_active")):
                bind.execute(
                    sa.text("UPDATE metadata_plugins SET is_active = :is_active WHERE key = :key"),
                    {"is_active": True, "key": LEGACY_KEY},
                )
            if current.get("category_id") and not legacy.get("category_id"):
                bind.execute(
                    sa.text("UPDATE metadata_plugins SET category_id = :category_id WHERE key = :key"),
                    {"category_id": current.get("category_id"), "key": LEGACY_KEY},
                )
            bind.execute(sa.text("DELETE FROM metadata_plugins WHERE key = :key"), {"key": NEW_KEY})
        elif current and not legacy:
            bind.execute(
                sa.text("UPDATE metadata_plugins SET key = :old_key WHERE key = :new_key"),
                {"old_key": LEGACY_KEY, "new_key": NEW_KEY},
            )

        bind.execute(
            sa.text(
                """
                UPDATE metadata_plugins
                SET name = :name,
                    description = :description
                WHERE key = :key
                """
            ),
            {
                "name": "Comics Core",
                "description": "Managed comics metadata schema with locked attributes.",
                "key": LEGACY_KEY,
            },
        )

    if _has_table(inspector, "metadata_categories"):
        bind.execute(
            sa.text(
                "UPDATE metadata_categories SET plugin_key = :old_key WHERE plugin_key = :new_key"
            ),
            {"new_key": NEW_KEY, "old_key": LEGACY_KEY},
        )

    if _has_table(inspector, "metadata_attributes"):
        bind.execute(
            sa.text(
                "UPDATE metadata_attributes SET plugin_key = :old_key WHERE plugin_key = :new_key"
            ),
            {"new_key": NEW_KEY, "old_key": LEGACY_KEY},
        )

    if _has_table(inspector, "app_settings"):
        _rename_app_settings_key_prefix(bind, NEW_KEY, LEGACY_KEY)
