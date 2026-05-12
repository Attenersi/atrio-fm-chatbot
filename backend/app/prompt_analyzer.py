"""Review-driven prompt analyzer.

Takes reviewer feedback collected on `training_examples` (human_notes,
reasoning, ideal_output, correction_type) and asks the LLM for concrete
short rules to append to the system prompt. Optionally accepts a list of
previously discarded suggestions so the model does not repeat them.

A single LLM call covers all groups; the call is throttled by the global
NVIDIA RPM bucket inside `llm.achat`. Output schema matches the existing
frontend / cache contract: `groups[].suggested_change` plus optional
`rag_suggestions[]`.

Override-cache freshness:
    The analyzer cache key incorporates the *current* active-override
    fingerprint at the moment of the API call. Phase 3 wired
    :func:`database.get_active_prompt_overrides` to the
    ``meta.rules_version`` token, which is bumped inside the same SQL
    transaction as every apply / rollback / consolidate. As a result,
    other uvicorn workers always read the up-to-date snapshot before
    serving the next chat request, so the analyzer cache key and the
    chat path agree on the same active rule set.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .config import (
    ANALYZER_LLM_TIMEOUT_SECONDS,
    ANALYZER_MAX_EXAMPLES_PER_GROUP,
    ANALYZER_MAX_GROUPS,
    ANALYZER_MAX_OUTPUT_TOKENS,
    LLM_ANALYZER_MODEL,
    LLM_TEMPERATURE,
)
from .llm import achat
from .llm_profiles import ResolvedLlmProfile


_log = logging.getLogger("fm.analyzer")


# ---------------------------------------------------------------------------
# Pydantic schema (single source of truth for analyzer output).
# Replaces the homegrown _parse_generic_json + json5 + json_repair layers.
# ---------------------------------------------------------------------------
class _AnalyzerGroup(BaseModel):
    type: str = ""
    suggested_change: str = ""
    rationale: str = ""
    confidence: float = 0.5
    affected_ids: list[int] = Field(default_factory=list)


class _AnalyzerRag(BaseModel):
    type: str = "rag_indexing"
    description: str = ""
    affected_ids: list[int] = Field(default_factory=list)


class AnalyzerOutput(BaseModel):
    groups: list[_AnalyzerGroup] = Field(default_factory=list)
    rag_suggestions: list[_AnalyzerRag] = Field(default_factory=list)


# Server-side guard: at most this many LLM calls per analyzer invocation
# (1 initial + 1 retry on validation error). The legacy multi-attempt /
# repair-LLM path is gone.
_ANALYZER_LLM_ATTEMPTS = 2


_ANALYZER_JSON_SCHEMA: dict[str, Any] = {
    "name": "AnalyzerOutput",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string"},
                        "suggested_change": {"type": "string"},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "affected_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": [
                        "type",
                        "suggested_change",
                        "rationale",
                        "confidence",
                        "affected_ids",
                    ],
                },
            },
            "rag_suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string"},
                        "description": {"type": "string"},
                        "affected_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["type", "description", "affected_ids"],
                },
            },
        },
        "required": ["groups", "rag_suggestions"],
    },
}


def _strip_json_fences(raw: str) -> str:
    """Trim ``` ... ``` fences. Structured outputs should never produce them
    but a few NIM models still do. Anything else (trailing commas, stray
    prose) now causes a deterministic ValidationError rather than triggering
    a retry storm — Pydantic owns parsing."""
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


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

Reviewers manually inspect chatbot answers and leave structured feedback on each
training example: a `human_notes` field (free text describing what was wrong),
a `reasoning` field (free text explaining the correction), an `ideal_output`
JSON (what the chatbot should have produced), and a `correction_type`:
  - "edited": reviewer changed the chatbot output (treat as a correction signal),
  - "rejected": reviewer rejected the chatbot's response entirely (treat as a
    strong negative signal — the rule that produced this answer is broken).

You will be given:
- The current SYSTEM_PROMPT used by the chatbot.
- A list of review groups, each carrying a few representative examples with
  human_notes, reasoning, the chatbot's actual output, and the reviewer's
  ideal_output.
- An optional list of `previously_discarded` suggestions a previous analyzer
  run produced and a human rejected. Do NOT repeat ideas equivalent to those.

Your job is to suggest 1-3 CONCRETE, short, additive rules per group that can
be appended at the end of the system prompt and would prevent the kind of
mistake reviewers flagged. Rules should:
- be 1-2 sentences,
- reference concrete signals from the inputs (keywords, situations),
- never rewrite the existing prompt, only extend it.

If a group's signal is "the chatbot did not have the facts in context" (i.e.
the issue is retrieval rather than instruction), do NOT propose a prompt rule.
Emit a `rag_suggestions` entry instead describing what the docs/index need.

Return STRICT JSON ONLY (no markdown, no commentary), matching this schema.
Use double quotes for every key and string. Inside string values, escape
double quotes as \\", backslashes as \\\\, and newlines as \\n.

{
  "groups": [
    {
      "type": "<bucket label from input>",
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


async def _analyzer_llm(
    messages: list[dict[str, str]],
    *,
    llm_profile: ResolvedLlmProfile | None = None,
) -> str:
    """Single LLM call with structured-output enforcement.

    Tries the strict ``json_schema`` mode first (OpenAI / latest NIM). If the
    server rejects either response_format kind, falls back to ``json_object``
    and finally a plain completion. Pydantic validation upstream rejects bad
    payloads regardless of which mode succeeded.
    """
    base_kwargs = dict(
        temperature=LLM_TEMPERATURE,
        model=None if llm_profile else LLM_ANALYZER_MODEL,
        timeout=float(ANALYZER_LLM_TIMEOUT_SECONDS),
        max_retries=0,
        max_tokens=ANALYZER_MAX_OUTPUT_TOKENS,
        resolved=llm_profile,
    )
    try:
        return await achat(
            messages,
            response_format={"type": "json_schema", "json_schema": _ANALYZER_JSON_SCHEMA},
            **base_kwargs,
        )
    except Exception as exc:
        _log.warning(
            "analyzer json_schema response_format failed (%s); retrying with json_object",
            exc,
        )
    try:
        return await achat(
            messages,
            response_format={"type": "json_object"},
            **base_kwargs,
        )
    except Exception as exc:
        _log.warning(
            "analyzer json_object response_format failed (%s); retrying plain completion",
            exc,
        )
    return await achat(messages, **base_kwargs)


def _shorten(text: str, limit: int) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "..."


def _diff_outputs(actual: dict[str, Any], ideal: dict[str, Any]) -> dict[str, Any]:
    """Compact before/after diff focused on classification fields. Avoids
    dumping entire response strings into the analyzer payload."""
    diff: dict[str, Any] = {}
    for key in ("category", "priority", "create_ticket", "department", "issue_summary"):
        a = actual.get(key) if isinstance(actual, dict) else None
        i = ideal.get(key) if isinstance(ideal, dict) else None
        if a != i and (a is not None or i is not None):
            diff[key] = {"actual": a, "ideal": i}
    actual_resp = ""
    ideal_resp = ""
    if isinstance(actual, dict):
        actual_resp = str(actual.get("response", "") or "")
    if isinstance(ideal, dict):
        ideal_resp = str(ideal.get("response", "") or "")
    if ideal_resp and ideal_resp != actual_resp:
        diff["response"] = {
            "actual": _shorten(actual_resp, 200),
            "ideal": _shorten(ideal_resp, 200),
        }
    return diff


def compact_training_example_for_analysis_api(item: dict[str, Any]) -> dict[str, Any]:
    """Slim training row for the training-quality analyzer API / UI.

    Matches the shape embedded in the analyzer LLM user payload (shortened
    strings, structured diff only).
    """
    actual = item.get("actual_output") or item.get("actual_payload") or {}
    ideal = item.get("ideal_output") or item.get("expected_payload") or {}
    return {
        "id": int(item["id"]),
        "input": _shorten(str(item.get("input_text") or ""), 280),
        "human_notes": _shorten(str(item.get("human_notes") or ""), 320),
        "reasoning": _shorten(str(item.get("reasoning") or ""), 320),
        "correction_type": str(item.get("correction_type") or ""),
        "diff": _diff_outputs(
            actual if isinstance(actual, dict) else {},
            ideal if isinstance(ideal, dict) else {},
        ),
    }


def _format_user_payload(
    groups: list[dict[str, Any]],
    current_prompt: str,
    discarded: list[dict[str, Any]] | None = None,
) -> str:
    """Build the user message for the analyzer LLM call. Trims to
    ANALYZER_MAX_GROUPS / ANALYZER_MAX_EXAMPLES_PER_GROUP and drops fields the
    model doesn't need (e.g. raw mismatch_fields) so prompt size stays sane."""
    trimmed_groups: list[dict[str, Any]] = []
    for group in groups[:ANALYZER_MAX_GROUPS]:
        examples_in = group.get("examples") or []
        compact_examples: list[dict[str, Any]] = []
        for ex in examples_in[:ANALYZER_MAX_EXAMPLES_PER_GROUP]:
            actual = ex.get("actual_output") or ex.get("actual_payload") or {}
            ideal = ex.get("ideal_output") or ex.get("expected_payload") or {}
            compact_examples.append(
                {
                    "id": ex.get("id"),
                    "input": _shorten(str(ex.get("input_text") or ""), 280),
                    "human_notes": _shorten(str(ex.get("human_notes") or ""), 320),
                    "reasoning": _shorten(str(ex.get("reasoning") or ""), 320),
                    "correction_type": ex.get("correction_type") or "",
                    "diff": _diff_outputs(actual, ideal),
                }
            )
        trimmed_groups.append(
            {
                "type": group.get("type"),
                "count": group.get("count"),
                "affected_ids": (group.get("affected_ids") or [])[
                    : ANALYZER_MAX_EXAMPLES_PER_GROUP * 4
                ],
                "examples": compact_examples,
            }
        )

    discarded_block = ""
    if discarded:
        compact_discarded = [
            {
                "type": str(d.get("error_type") or "").strip(),
                "suggested_change": _shorten(str(d.get("suggested_change") or ""), 280),
                "reason": _shorten(str(d.get("reason") or ""), 200),
            }
            for d in discarded[:8]
            if str(d.get("suggested_change") or "").strip()
        ]
        if compact_discarded:
            discarded_block = (
                "\n\n## Previously discarded suggestions (do NOT repeat equivalent ideas):\n"
                + json.dumps(compact_discarded, ensure_ascii=False, indent=2)
            )

    return (
        "## Current SYSTEM_PROMPT (do not rewrite, only suggest additions):\n"
        f"{current_prompt}\n\n"
        "## Review groups (each with a few representative reviewer-tagged examples):\n"
        f"{json.dumps(trimmed_groups, ensure_ascii=False, indent=2)}"
        f"{discarded_block}\n\n"
        "Return JSON only, matching the documented schema."
    )


def _validate_and_normalize(raw_text: str, *, model_label: str) -> AnalysisResult:
    """Parse via Pydantic. Raises ``ValidationError`` on schema mismatch so the
    caller can issue exactly one retry; otherwise returns a normalized result."""
    cleaned = _strip_json_fences(raw_text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationError.from_exception_data(
            "AnalyzerOutput",
            [
                {
                    "type": "json_invalid",
                    "loc": ("root",),
                    "msg": f"Analyzer returned non-JSON: {exc.msg}",
                    "input": cleaned[:200],
                    "ctx": {"error": str(exc)},
                }
            ],
        ) from exc
    parsed = AnalyzerOutput.model_validate(payload)
    if not parsed.groups and not parsed.rag_suggestions:
        raise ValidationError.from_exception_data(
            "AnalyzerOutput",
            [
                {
                    "type": "value_error",
                    "loc": ("groups",),
                    "msg": "Analyzer returned no usable groups or rag_suggestions",
                    "input": payload,
                    "ctx": {"error": "empty"},
                }
            ],
        )
    return AnalysisResult(
        groups=[g.model_dump() for g in parsed.groups],
        rag_suggestions=[r.model_dump() for r in parsed.rag_suggestions],
        model=model_label,
        raw_text=raw_text,
    )


async def analyze_pending_async(
    groups: list[dict[str, Any]],
    current_prompt: str,
    *,
    discarded: list[dict[str, Any]] | None = None,
    llm_profile: ResolvedLlmProfile | None = None,
) -> AnalysisResult:
    """One LLM call (with up to one retry on validation failure) for all groups.

    `groups` items follow the shape returned by
    `database.list_review_signals_for_analysis(...)`: each group has `type`,
    `count`, `affected_ids`, `examples` (with `input_text`, `human_notes`,
    `reasoning`, `actual_output`, `ideal_output`, `correction_type`).

    The output schema is enforced by Pydantic (``AnalyzerOutput``); the LLM
    request also pins ``response_format=json_schema``. There is no separate
    repair LLM pass anymore — if both attempts fail validation we raise.
    """
    model_label = (
        llm_profile.default_model if llm_profile is not None else LLM_ANALYZER_MODEL
    )
    if not groups:
        return AnalysisResult(
            groups=[], rag_suggestions=[], model=model_label, raw_text=""
        )

    user_payload = _format_user_payload(groups, current_prompt, discarded=discarded)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    last_error: Exception | None = None
    for attempt in range(_ANALYZER_LLM_ATTEMPTS):
        try:
            text = await _analyzer_llm(messages, llm_profile=llm_profile)
            return _validate_and_normalize(text, model_label=model_label)
        except ValidationError as exc:
            last_error = exc
            _log.warning(
                "analyzer attempt %d failed Pydantic validation: %s",
                attempt + 1,
                exc,
            )
            if attempt >= _ANALYZER_LLM_ATTEMPTS - 1:
                break
            messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Your last response failed schema validation:\n"
                        f"{exc}\n"
                        "Return ONLY one JSON object that matches the AnalyzerOutput "
                        "schema (groups + rag_suggestions, both arrays). No prose, no "
                        "markdown fences."
                    ),
                }
            ]
            continue
        except Exception as exc:
            last_error = exc
            _log.warning("analyzer attempt %d failed: %s", attempt + 1, exc)
            break
    raise RuntimeError(f"Analyzer failed after retry: {last_error}")
