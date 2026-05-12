"""meta table with rules_version + db_salt

Tiny key/value table the rest of the codebase uses to:

- bump ``rules_version`` whenever the active prompt-override set changes,
  so multi-worker chat handlers know to refresh their local snapshot
  (replaces the old in-process 30 s TTL cache).
- store a per-deployment ``db_salt`` that ``llm_crypto`` mixes into PBKDF2
  key derivation for encrypted LLM API keys.

Revision ID: 0003_meta_table
Revises: 0002_prompt_override_examples
Create Date: 2026-05-10
"""
from __future__ import annotations

import secrets
from typing import Sequence, Union

from alembic import op


revision: str = "0003_meta_table"
down_revision: Union[str, None] = "0002_prompt_override_examples"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    bind.exec_driver_sql(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('rules_version', '1')"
    )
    salt = secrets.token_urlsafe(32)
    bind.exec_driver_sql(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('db_salt', ?)",
        (salt,),
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TABLE IF EXISTS meta")
