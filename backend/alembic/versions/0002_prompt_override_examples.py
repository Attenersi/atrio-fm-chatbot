"""prompt_override_examples junction table

Replaces the JSON-blob ``prompt_overrides.affected_example_ids`` column with a
proper many-to-many table. The legacy JSON column stays in place for one
release as a fallback (dropped in revision 0004).

Backfill: read every existing override row, parse JSON, and insert junction
rows. ``INSERT OR IGNORE`` keeps the migration idempotent if the table is
partially populated already.

Revision ID: 0002_prompt_override_examples
Revises: 0001_baseline
Create Date: 2026-05-10
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_prompt_override_examples"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS prompt_override_examples (
            override_id INTEGER NOT NULL,
            example_id INTEGER NOT NULL,
            PRIMARY KEY (override_id, example_id)
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_poe_example ON prompt_override_examples(example_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_poe_override ON prompt_override_examples(override_id)"
    )

    # Backfill from legacy JSON column. Tolerate rows where the column does
    # not yet exist (fresh install path) or holds malformed JSON.
    try:
        rows = bind.exec_driver_sql(
            "SELECT id, affected_example_ids FROM prompt_overrides"
        ).fetchall()
    except Exception:
        rows = []

    for row in rows:
        try:
            override_id = int(row[0])
        except (TypeError, ValueError):
            continue
        raw = row[1] or "[]"
        try:
            ids = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            ids = []
        if not isinstance(ids, list):
            continue
        for x in ids:
            try:
                eid = int(x)
            except (TypeError, ValueError):
                continue
            bind.exec_driver_sql(
                "INSERT OR IGNORE INTO prompt_override_examples "
                "(override_id, example_id) VALUES (?, ?)",
                (override_id, eid),
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP INDEX IF EXISTS idx_poe_example")
    bind.exec_driver_sql("DROP INDEX IF EXISTS idx_poe_override")
    bind.exec_driver_sql("DROP TABLE IF EXISTS prompt_override_examples")
