"""Connection + bootstrap helpers (initial database setup, JSON utils).

Phase-4 transitional shim: real implementations still live in
``app.database`` and are re-exported here so callers can already use the
new namespace.
"""

from ..database import (
    SQLITE_DB_PATH,
    get_conn,
    init_db,
    normalize_status,
    _utc_now_iso,
    _json_dump,
    _json_load,
)

__all__ = [
    "SQLITE_DB_PATH",
    "get_conn",
    "init_db",
    "normalize_status",
    "_utc_now_iso",
    "_json_dump",
    "_json_load",
]
