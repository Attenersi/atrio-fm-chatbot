"""baseline

Documents the legacy schema established by the imperative ``init_db()`` in
:mod:`app.database`. This revision intentionally does not recreate the
schema — fresh installations get the schema from ``init_db()`` first, then
``alembic upgrade head`` stamps this revision and applies 0002+ on top.

Existing deployments stamp this revision automatically on first run via
:func:`app.db_migrations.run_migrations` (which calls ``alembic stamp 0001_baseline``
when the alembic_version table is empty but the legacy schema already exists).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-10
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
