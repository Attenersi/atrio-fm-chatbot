"""Drop legacy prompt_overrides.affected_example_ids JSON column

Phase 2 (revision 0002) introduced the ``prompt_override_examples``
junction table and backfilled it from this JSON column. After one
release on the new shape, the column has no readers left in the code
base — the application layer always reads through the junction table
and only falls back to the legacy column inside ``_override_example_ids``
for safety.

This migration removes the column. SQLite ≥ 3.35 supports
``ALTER TABLE ... DROP COLUMN`` directly; for older builds we fall back
to the standard table-rebuild pattern (CREATE TABLE new; INSERT SELECT;
DROP old; ALTER TABLE new RENAME).

Revision ID: 0004_drop_legacy_affected_ids
Revises: 0003_meta_table
Create Date: 2026-05-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0004_drop_legacy_affected_ids"
down_revision: Union[str, None] = "0003_meta_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "error_type TEXT NOT NULL",
    "suggested_change TEXT NOT NULL DEFAULT ''",
    "approved_change TEXT NOT NULL",
    "rationale TEXT NOT NULL DEFAULT ''",
    "status TEXT NOT NULL DEFAULT 'pending'",
    "created_by_user_id INTEGER",
    "created_at TEXT NOT NULL",
    "activated_at TEXT",
    "deactivated_at TEXT",
    "eval_baseline_id INTEGER",
    "eval_after_id INTEGER",
    "replay_summary_json TEXT NOT NULL DEFAULT '{}'",
)

_NEW_TABLE_SQL = (
    "CREATE TABLE prompt_overrides_new (\n    "
    + ",\n    ".join(_NEW_COLUMNS)
    + "\n)"
)

_KEPT_COLS = (
    "id, error_type, suggested_change, approved_change, rationale, status, "
    "created_by_user_id, created_at, activated_at, deactivated_at, "
    "eval_baseline_id, eval_after_id, replay_summary_json"
)


def _column_exists(bind, table: str, column: str) -> bool:
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _drop_column_native(bind) -> bool:
    try:
        bind.exec_driver_sql(
            "ALTER TABLE prompt_overrides DROP COLUMN affected_example_ids"
        )
        return True
    except Exception:
        return False


def _drop_column_rebuild(bind) -> None:
    bind.exec_driver_sql(_NEW_TABLE_SQL)
    bind.exec_driver_sql(
        f"INSERT INTO prompt_overrides_new ({_KEPT_COLS}) "
        f"SELECT {_KEPT_COLS} FROM prompt_overrides"
    )
    bind.exec_driver_sql("DROP TABLE prompt_overrides")
    bind.exec_driver_sql(
        "ALTER TABLE prompt_overrides_new RENAME TO prompt_overrides"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_prompt_overrides_status "
        "ON prompt_overrides(status)"
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "prompt_overrides", "affected_example_ids"):
        return

    if not _drop_column_native(bind):
        _drop_column_rebuild(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "prompt_overrides", "affected_example_ids"):
        return
    bind.exec_driver_sql(
        "ALTER TABLE prompt_overrides "
        "ADD COLUMN affected_example_ids TEXT NOT NULL DEFAULT '[]'"
    )
    # Best-effort restore of the JSON column from the junction table; the
    # column is purely a denormalized cache so the contents map cleanly.
    bind.exec_driver_sql(
        """
        UPDATE prompt_overrides
        SET affected_example_ids = (
            SELECT '[' || COALESCE(GROUP_CONCAT(example_id, ','), '') || ']'
            FROM prompt_override_examples
            WHERE override_id = prompt_overrides.id
        )
        """
    )
