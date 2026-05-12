"""Question-bank join: who has already claimed which training examples.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    covered_example_ids_from_active_overrides,
    get_question_bank_claimed_example_ids,
    insert_training_question_prompt_events,
    list_question_bank_rows,
    question_bank_dedup_cache_tag,
    record_suggestion_affected_from_analysis_payload,
    suppress_review_signals,
)

__all__ = [
    "covered_example_ids_from_active_overrides",
    "get_question_bank_claimed_example_ids",
    "insert_training_question_prompt_events",
    "list_question_bank_rows",
    "question_bank_dedup_cache_tag",
    "record_suggestion_affected_from_analysis_payload",
    "suppress_review_signals",
]
