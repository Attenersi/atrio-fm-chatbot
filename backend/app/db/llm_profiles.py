"""LLM model profiles + per-task default selection.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    create_llm_model_profile,
    delete_llm_model_profile,
    fetch_llm_profile_row_for_resolve,
    get_llm_model_profile,
    get_llm_task_default_profile_id,
    list_llm_model_profiles,
    list_llm_task_defaults,
    set_llm_task_default,
    update_llm_model_profile,
)

__all__ = [
    "create_llm_model_profile",
    "delete_llm_model_profile",
    "fetch_llm_profile_row_for_resolve",
    "get_llm_model_profile",
    "get_llm_task_default_profile_id",
    "list_llm_model_profiles",
    "list_llm_task_defaults",
    "set_llm_task_default",
    "update_llm_model_profile",
]
