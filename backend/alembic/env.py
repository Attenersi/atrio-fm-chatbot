"""Alembic environment for the fm-chatbot SQLite DB.

We keep the schema declared imperatively in `database.init_db()` *and* in the
Alembic baseline. The baseline (revision 0001) creates the same tables/indexes
that legacy `init_db()` did so the very first `alembic upgrade head` against a
fresh database produces the exact same shape the rest of the codebase expects.
Subsequent migrations (0002+) layer on top.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import SQLITE_DB_PATH  # noqa: E402

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    except Exception:
        pass


def _resolve_sqlite_url() -> str:
    raw = os.getenv("ALEMBIC_SQLITE_URL", "").strip()
    if raw:
        return raw
    db_path = Path(SQLITE_DB_PATH)
    if not db_path.is_absolute():
        db_path = BACKEND_ROOT / db_path
    return f"sqlite:///{db_path.as_posix()}"


config.set_main_option("sqlalchemy.url", _resolve_sqlite_url())

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
