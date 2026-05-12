"""Eval-run bookkeeping (legacy baseline/after pipeline).

Phase-4 transitional shim: implementations still live in ``app.database``.
The eval-run flow is mostly deprecated (POST /eval/run returns 410 since
Phase 1) but the data model is kept around for historical inspection.
"""

from ..database import (
    create_eval_run,
    finalize_eval_run,
    get_eval_run,
    has_running_eval_run,
    latest_done_eval_run,
    list_eval_runs,
)

__all__ = [
    "create_eval_run",
    "finalize_eval_run",
    "get_eval_run",
    "has_running_eval_run",
    "latest_done_eval_run",
    "list_eval_runs",
]
