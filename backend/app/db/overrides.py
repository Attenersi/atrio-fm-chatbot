"""Prompt-override lifecycle + active-override snapshot.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    apply_prompt_override,
    consolidate_active_prompt_overrides,
    count_active_prompt_overrides,
    get_active_prompt_overrides,
    get_prompt_override,
    invalidate_active_overrides_cache,
    list_prompt_overrides,
    list_recent_suggestion_decisions,
    record_prompt_suggestion_decision,
    rollback_prompt_override,
    set_prompt_override_eval_after,
    set_prompt_override_replay_summary,
    supersede_all_active_prompt_overrides,
)

__all__ = [
    "apply_prompt_override",
    "consolidate_active_prompt_overrides",
    "count_active_prompt_overrides",
    "get_active_prompt_overrides",
    "get_prompt_override",
    "invalidate_active_overrides_cache",
    "list_prompt_overrides",
    "list_recent_suggestion_decisions",
    "record_prompt_suggestion_decision",
    "rollback_prompt_override",
    "set_prompt_override_eval_after",
    "set_prompt_override_replay_summary",
    "supersede_all_active_prompt_overrides",
]
