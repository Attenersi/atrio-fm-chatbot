"""Thin wrapper around Alembic so `init_db()` can drive migrations.

Strategy:
- Fresh install: ``init_db()`` runs `CREATE TABLE IF NOT EXISTS ...`, then we
  stamp the alembic baseline (0001) and apply 0002+ migrations.
- Existing install: same flow. `init_db()` is idempotent; we detect that the
  legacy schema is already present, stamp 0001, then upgrade to head.

We never invoke alembic's offline mode here — running in-process keeps SQLite
file paths consistent and avoids spawning subprocesses on Windows.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import SQLITE_DB_PATH

_log = logging.getLogger("fm.db_migrations")


def _alembic_config():
    """Build an Alembic Config pointing at backend/alembic from anywhere."""
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    db_path = Path(SQLITE_DB_PATH)
    if not db_path.is_absolute():
        db_path = backend_root / db_path
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def run_migrations() -> None:
    """Apply pending Alembic migrations against the configured SQLite file.

    Best-effort: if alembic is missing (e.g. minimal CI image) we log and
    return so legacy `init_db()` still produces a usable DB.
    """
    try:
        from alembic import command
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
    except Exception as exc:
        _log.warning("alembic unavailable, skipping migrations: %s", exc)
        return

    cfg = _alembic_config()
    url = cfg.get_main_option("sqlalchemy.url")
    if not url:
        _log.warning("alembic sqlalchemy.url unresolved, skipping migrations")
        return

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
        if current is None:
            command.stamp(cfg, "0001_baseline")
        command.upgrade(cfg, "head")
    except Exception:
        _log.exception("alembic migrations failed")
