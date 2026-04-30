"""Faza D: LLM-based prompt analyzer.

Takes the grouped pending mismatches (from Faza B) and the current SYSTEM_PROMPT,
asks the LLM for concrete prompt-text suggestions per group, plus separate
RAG-fix suggestions for retrieval failures. Result is cached by hash of the
pending example IDs in `prompt_analysis_cache`.

Single LLM call per analysis (not per group) to stay friendly with the global
NVIDIA 40 RPM budget. The call goes through llm.achat() which already acquires
the global RPM token before talking to NVIDIA."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .config import (
    ANALYZER_MAX_EXAMPLES_PER_GROUP,
    ANALYZER_MAX_GROUPS,
    LLM_ANALYZER_MODEL,
)
from .llm import achat


def _parse_generic_json(raw: str) -> dict[str, Any]:
    """Parse JSON tolerating ```json fences and stray prose around the object."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Fall back to outermost {...} block.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])

_log = logging.getLogger("fm.analyzer")


@dataclass
class AnalysisResult:
    groups: list[dict[str, Any]]
    rag_suggestions: list[dict[str, Any]]
    model: str
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": self.groups,
            "rag_suggestions": self.rag_suggestions,
            "model": self.model,
        }


_RAG_TYPES = {"response_tokens_missing"}

_SYSTEM_PROMPT = """You are a prompt-engineering reviewer for a Facility Management chatbot.
You will be given:
- The current SYSTEM_PROMPT used by the chatbot.
- A list of error groups (mismatches between the bot's classification and the
  expected ground truth from a test suite).

Your job is to suggest CONCRETE one- or two-sentence rules to ADD AT THE END of
the system prompt that would have prevented these mismatches. Do not rewrite
the whole prompt; only propose minimal, targeted additional rules.

For groups that look like RAG retrieval failures (the bot did not have the
needed facts in context), do NOT suggest a prompt change. Instead emit a
`rag_suggestions` entry describing what the indexing pipeline likely needs.

Return STRICT JSON ONLY (no markdown, no commentary), matching this schema:
{
  "groups": [
    {
      "type": "<error type from input>",
      "suggested_change": "<single short paragraph to append>",
      "rationale": "<one sentence explaining why this rule helps>",
      "confidence": <number between 0 and 1>,
      "affected_ids": [<ints from input>]
    }
  ],
  "rag_suggestions": [
    {
      "type": "rag_chunking" | "rag_indexing" | "rag_query",
      "description": "<concrete change to docs/chunking>",
      "affected_ids": [<ints from input>]
    }
  ]
}
"""


def _format_user_payload(groups: list[dict[str, Any]], current_prompt: str) -> str:
    """Build the user message for the analyzer LLM call.
    Truncate to ANALYZER_MAX_GROUPS / ANALYZER_MAX_EXAMPLES_PER_GROUP to keep
    request size predictable."""
    trimmed: list[dict[str, Any]] = []
    for group in groups[:ANALYZER_MAX_GROUPS]:
        trimmed.append(
            {
                "type": group.get("type"),
                "count": group.get("count"),
                "rag_signal": bool(group.get("rag_signal")),
                "examples": group.get("examples_preview", [])[:ANALYZER_MAX_EXAMPLES_PER_GROUP],
                "affected_ids": group.get("affected_ids", [])[:ANALYZER_MAX_EXAMPLES_PER_GROUP],
            }
        )
    return (
        "## Current SYSTEM_PROMPT (do not rewrite, only suggest additions):\n"
        f"{current_prompt}\n\n"
        "## Error groups (each with a few representative pending examples):\n"
        f"{json.dumps(trimmed, ensure_ascii=False, indent=2)}\n\n"
        "Return JSON only, matching the documented schema."
    )


def _validate_and_normalize(raw_text: str) -> AnalysisResult:
    """Parse raw LLM output (which may have stray markdown). Raises on
    unrecoverable structural problems so the caller can retry once."""
    payload = _parse_generic_json(raw_text)
    groups_in = payload.get("groups") or []
    rag_in = payload.get("rag_suggestions") or []

    norm_groups: list[dict[str, Any]] = []
    for g in groups_in if isinstance(groups_in, list) else []:
        if not isinstance(g, dict):
            continue
        norm_groups.append(
            {
                "type": str(g.get("type", "")).strip(),
                "suggested_change": str(g.get("suggested_change", "")).strip(),
                "rationale": str(g.get("rationale", "")).strip(),
                "confidence": _clamp01(g.get("confidence")),
                "affected_ids": [int(x) for x in (g.get("affected_ids") or []) if str(x).isdigit() or isinstance(x, int)],
            }
        )
    norm_rag: list[dict[str, Any]] = []
    for r in rag_in if isinstance(rag_in, list) else []:
        if not isinstance(r, dict):
            continue
        norm_rag.append(
            {
                "type": str(r.get("type", "rag_indexing")).strip(),
                "description": str(r.get("description", "")).strip(),
                "affected_ids": [int(x) for x in (r.get("affected_ids") or []) if str(x).isdigit() or isinstance(x, int)],
            }
        )
    if not norm_groups and not norm_rag:
        raise ValueError("Analyzer returned no usable groups or rag_suggestions")
    return AnalysisResult(
        groups=norm_groups,
        rag_suggestions=norm_rag,
        model=LLM_ANALYZER_MODEL,
        raw_text=raw_text,
    )


def _clamp01(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


async def analyze_pending_async(
    groups: list[dict[str, Any]],
    current_prompt: str,
) -> AnalysisResult:
    """Make ONE LLM call (with one retry on parse error) to get suggestions for
    all groups at once."""
    if not groups:
        return AnalysisResult(groups=[], rag_suggestions=[], model=LLM_ANALYZER_MODEL, raw_text="")

    user_payload = _format_user_payload(groups, current_prompt)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            text = await achat(messages, temperature=0.0, model=LLM_ANALYZER_MODEL)
            return _validate_and_normalize(text)
        except Exception as exc:
            last_error = exc
            _log.warning("analyzer call attempt %d failed: %s", attempt + 1, exc)
            if attempt == 0:
                # Strengthen the JSON-only directive on retry.
                messages = messages + [
                    {
                        "role": "user",
                        "content": "Your previous response was not valid JSON. Return ONLY the JSON object, no prose, no markdown.",
                    }
                ]
                continue
            break
    raise RuntimeError(f"Analyzer failed after retry: {last_error}")
