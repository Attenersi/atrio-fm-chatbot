"""Backend persistence layer, namespaced by domain.

This package is the long-term home for what historically lived as one big
``app.database`` module. To keep the migration safe and reversible, the
actual function bodies still live in ``app.database`` for now and each
sub-module here re-exports just the slice it owns.

Callers should prefer the namespaced imports going forward:

    from app.db.users import authenticate_user
    from app.db.overrides import apply_prompt_override

The legacy ``from app.database import ...`` form keeps working for one
release; afterwards ``database.py`` will be reduced to a thin shim that
forwards to this package and finally removed.
"""

from . import (
    _conn,
    audit,
    cache,
    eval,
    llm_profiles,
    meta,
    overrides,
    question_bank,
    training,
    users,
)

__all__ = [
    "_conn",
    "audit",
    "cache",
    "eval",
    "llm_profiles",
    "meta",
    "overrides",
    "question_bank",
    "training",
    "users",
]
