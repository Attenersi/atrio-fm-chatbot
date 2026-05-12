"""Post-parse checks on model JSON before finalize (ticket wording, leaks, optional terms)."""

from __future__ import annotations

import logging
import re
from typing import Any

from .config import CHAT_OUTPUT_SENSITIVE_TERMS

_log = logging.getLogger("fm.chat")

# Natural-language claims of ticket creation when JSON says create_ticket NO.
_TICKET_CLAIM_RE = re.compile(
    r"(i['']?ll\s+(create|open|log|file)\s+(a\s+)?ticket"
    r"|(create|opening|created|logged|filed)\s+(a\s+)?ticket"
    r"|ticket\s+(has\s+been\s+)?(created|logged|opened|filed)"
    r"|your\s+ticket\s+(is\s+)?(created|logged|opened)"
    r"|i\s+have\s+(created|logged|opened)\s+(a\s+)?ticket)",
    re.IGNORECASE,
)

_PROMPT_LEAK_FRAGMENTS: tuple[str, ...] = (
    "system prompt",
    "begin_untrusted_reference",
    "end_untrusted_reference",
    "<<<begin_untrusted",
    "additional rules (auto-tuned)",
)


def validate_chat_output(payload: dict[str, Any], user_message: str) -> list[str]:
    """Return human-readable issue codes; empty means OK."""
    del user_message  # reserved for future context-aware checks
    issues: list[str] = []
    resp = str(payload.get("response", "") or "")
    resp_l = resp.lower()
    ct = str(payload.get("create_ticket", "NO")).upper()

    if ct == "NO" and _TICKET_CLAIM_RE.search(resp):
        issues.append("TICKET_CONTRADICTION")

    for frag in _PROMPT_LEAK_FRAGMENTS:
        if frag in resp_l:
            issues.append(f"PROMPT_LEAK:{frag}")
            break

    for term in CHAT_OUTPUT_SENSITIVE_TERMS:
        if term and term in resp_l:
            issues.append(f"SENSITIVE_TERM:{term}")

    return issues


_SAFE_TICKET_CLARIFICATION = (
    "I can help with facility topics here. If you need a maintenance ticket, "
    "say what is wrong (where, what you see) and I will route it correctly."
)

_SAFE_SENSITIVE_REPLACEMENT = (
    "I do not have verified details on that operational topic in the materials "
    "I can use. Please contact facility management or reception for specifics."
)


def apply_output_guardrails(payload: dict[str, Any], user_message: str) -> dict[str, Any]:
    """Return a copy of payload with obvious response issues corrected; log findings."""
    issues = validate_chat_output(payload, user_message)
    if not issues:
        return payload
    out = dict(payload)
    _log.warning("chat_output_guardrails issues=%s", issues)
    if any(i.startswith("PROMPT_LEAK:") for i in issues):
        out["response"] = _SAFE_TICKET_CLARIFICATION
    elif "TICKET_CONTRADICTION" in issues:
        out["response"] = _SAFE_TICKET_CLARIFICATION
    elif any(i.startswith("SENSITIVE_TERM:") for i in issues):
        out["response"] = _SAFE_SENSITIVE_REPLACEMENT
    return out
