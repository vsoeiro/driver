"""normalize_jobs_payload_result_json

Revision ID: a3d9f1c7b2e4
Revises: f2c7b8d91a4e
Create Date: 2026-02-16 23:35:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3d9f1c7b2e4"
down_revision: Union[str, Sequence[str], None] = "f2c7b8d91a4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION _driver_try_parse_json(input_text text)
        RETURNS json
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF input_text IS NULL OR btrim(input_text) = '' THEN
            RETURN NULL;
          END IF;
          RETURN input_text::json;
        EXCEPTION
          WHEN others THEN
            RETURN NULL;
        END;
        $$;
        """
    )

    op.execute(
        """
        ALTER TABLE jobs
          ALTER COLUMN payload TYPE json USING COALESCE(_driver_try_parse_json(payload), '{}'::json),
          ALTER COLUMN result TYPE json USING _driver_try_parse_json(result);
        """
    )

    op.execute("DROP FUNCTION IF EXISTS _driver_try_parse_json(text);")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE jobs
          ALTER COLUMN payload TYPE text USING payload::text,
          ALTER COLUMN result TYPE text USING result::text;
        """
    )
