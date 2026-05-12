"""Prompt-override audit log.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    list_prompt_override_audit,
    record_prompt_override_audit,
)

__all__ = [
    "list_prompt_override_audit",
    "record_prompt_override_audit",
]
