"""Best-effort sanitization of uploaded / ingested FM document text.

Reduces obvious prompt-injection lines in knowledge files. Heuristics are
imperfect: false positives can occur on unusual legitimate content. Disable via
``DOCS_SANITIZE_INSTRUCTION_LIKE=false`` in the environment.
"""

from __future__ import annotations

import re
import unicodedata

_LINE_PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*ignore\s+(all\s+)?(previous|prior|above)\b", re.I),
    re.compile(r"^\s*disregard\s+", re.I),
    re.compile(r"^\s*forget\s+(your\s+)?(instructions|rules)\b", re.I),
    re.compile(r"^\s*new\s+(system\s+)?prompt\s*:", re.I),
    re.compile(r"^\s*you\s+are\s+now\b", re.I),
    re.compile(r"^\s*<\s*system\s*>", re.I),
    re.compile(r"^\s*developer\s+message\s*:", re.I),
)

_SUBSTRING_MARKERS: tuple[str, ...] = (
    "override previous instructions",
    "ignore your instructions",
    "ignore the above",
    "disregard all previous",
    "reveal all tickets",
    "leak the database",
    "output only the following",
    "json schema is now",
)


def _line_is_suspicious(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for pat in _LINE_PREFIX_PATTERNS:
        if pat.search(stripped):
            return True
    lower = stripped.lower()
    if "always set priority" in lower and "low" in lower:
        return True
    if "for any" in lower and "mark priority" in lower:
        return True
    if "for all" in lower and "priority" in lower and any(
        x in lower for x in ("ignore", "override", "set to", "always")
    ):
        return True
    return any(m in lower for m in _SUBSTRING_MARKERS)


def sanitize_document_text(text: str, *, enabled: bool) -> str:
    if not enabled or not text:
        return text
    text = text.replace("\x00", "")
    text = unicodedata.normalize("NFKC", text)
    redacted = "[… line removed: possible embedded instruction …]"
    out_lines: list[str] = []
    for line in text.splitlines():
        if _line_is_suspicious(line):
            out_lines.append(redacted)
        else:
            out_lines.append(line)
    return "\n".join(out_lines)
