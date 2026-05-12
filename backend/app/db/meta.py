"""Generic ``meta`` key/value store + rules-version token.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    delete_meta,
    get_meta,
    get_rules_version,
    set_meta,
)

__all__ = [
    "delete_meta",
    "get_meta",
    "get_rules_version",
    "set_meta",
]
