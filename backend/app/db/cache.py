"""Analysis-cache + housekeeping (vacuum) helpers.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    compute_pending_cache_key,
    compute_review_signals_cache_key,
    get_prompt_analysis_cache,
    put_prompt_analysis_cache,
    vacuum_training_quality_caches,
)

__all__ = [
    "compute_pending_cache_key",
    "compute_review_signals_cache_key",
    "get_prompt_analysis_cache",
    "put_prompt_analysis_cache",
    "vacuum_training_quality_caches",
]
