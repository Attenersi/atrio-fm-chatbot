"""LLM helper: merge many active prompt override texts into one rule block.

Uses Pydantic + ``response_format=json_schema`` for output validation. The
old json5 / json_repair / homegrown trailing-comma stripper layers are gone;
on the rare validation failure we issue exactly one retry with the validator
error fed back to the model.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .config import (
    ANALYZER_LLM_TIMEOUT_SECONDS,
    CONSOLIDATE_LINE_CLUSTER_THRESHOLD as _CONSOLIDATE_LINE_CLUSTER_THRESHOLD,
    LLM_ANALYZER_MODEL,
    LLM_TEMPERATURE,
)
from .llm import achat
from .llm_profiles import ResolvedLlmProfile
from .prompt_rule_similarity import rule_similarity

_log = logging.getLogger("fm.consolidator")

CONSOLIDATE_LINE_CLUSTER_THRESHOLD = _CONSOLIDATE_LINE_CLUSTER_THRESHOLD

# At most one retry on schema-validation failure; no LLM repair pass.
_CONSOLIDATOR_LLM_ATTEMPTS = 2

_SYSTEM = """You synthesize multiple "additional rules" for a facility-management chatbot into ONE coherent policy block for the system prompt.

Your job is NOT to concatenate or lightly edit source text. You must REWRITE.

Workflow:
1) Read all input groups. Each group lists lines that a heuristic marked as "similar theme" — treat them as one topic.
2) For each topic: merge duplicates and paraphrases into a single clear rule (one or two short sentences). Do not keep two bullets that say the same thing in different words.
3) Across topics: order logically (safety/urgent first, then tickets, then classification/tone, then misc).
4) If two topics conflict, prefer stricter safety, clearer user-facing behavior, and explicit escalation.
5) Write ``merged_rule`` as a concise policy: either numbered lines "1. ...\\n2. ..." OR short paragraphs separated by \\n. Use consistent voice (imperative or "The assistant must ...").
6) Do NOT copy-paste or quote original sentences verbatim. Use new wording that covers the same requirements.
7) ``rationale``: 2-4 sentences naming what you merged (e.g. "Combined smoke and fire urgency rules into one; unified two ticket-creation hints.").

Bad example (forbidden): pasting five original lines unchanged.
Good example: Input has "If smoke, URGENT" and "Smoke implies urgent priority" -> one line: "When the user reports smoke, fire, or burning odor, set priority to URGENT and treat as safety."

Output format: ONLY valid JSON with double-quoted keys and strings. No markdown fences.
Inside JSON strings use \\n for newlines - never raw line breaks inside a string value.

JSON shape:
{"merged_rule": "<string>", "rationale": "<string>"}
"""


_CONSOLIDATOR_JSON_SCHEMA: dict[str, Any] = {
    "name": "ConsolidatorOutput",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "merged_rule": {"type": "string", "minLength": 1},
            "rationale": {"type": "string"},
        },
        "required": ["merged_rule", "rationale"],
    },
}


class ConsolidatorOutput(BaseModel):
    merged_rule: str
    rationale: str = ""


def _strip_json_fences(raw: str) -> str:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def flatten_override_lines(rows: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Split each ``approved_change`` into non-empty lines with bullet junk stripped."""
    out: list[tuple[int, str]] = []
    for r in rows:
        try:
            oid = int(r["id"])
        except (TypeError, ValueError):
            continue
        body = (r.get("approved_change") or "").strip()
        if not body:
            continue
        added = False
        for raw in body.splitlines():
            s = raw.strip()
            if not s:
                continue
            s = re.sub(r"^[\s>*#\-•]+", "", s).strip()
            s = re.sub(r"^\d+[\).\s]+", "", s).strip()
            if s:
                out.append((oid, s))
                added = True
        if not added:
            out.append((oid, body))
    return out


def cluster_consolidator_lines(
    lines: list[tuple[int, str]],
    *,
    threshold: float = CONSOLIDATE_LINE_CLUSTER_THRESHOLD,
) -> list[list[tuple[int, str]]]:
    """Greedy clustering: each new line joins the cluster with highest max similarity."""
    clusters: list[list[tuple[int, str]]] = []
    for oid, line in lines:
        best_ci = -1
        best_score = 0.0
        for ci, cluster in enumerate(clusters):
            mx = max(rule_similarity(line, ex) for _, ex in cluster)
            if mx >= threshold and mx > best_score:
                best_score = mx
                best_ci = ci
        if best_ci >= 0:
            clusters[best_ci].append((oid, line))
        else:
            clusters.append([(oid, line)])
    return clusters


def build_consolidator_user_message(rows: list[dict[str, Any]]) -> str:
    """User message for the merge LLM: clustered lines + metadata."""
    flat = flatten_override_lines(rows)
    clusters = cluster_consolidator_lines(flat) if flat else []

    parts: list[str] = [
        "## Instructions",
        "Each ### Group below contains lines our heuristic thinks are similar in meaning.",
        "Produce ONE synthesized rule per group (merge duplicates and paraphrases). Then combine all groups into merged_rule.",
        "",
    ]
    if not clusters:
        parts.append("(No line-level clusters; use full override bodies below.)")
        parts.append("")
        for r in rows:
            oid = r.get("id")
            et = r.get("error_type") or ""
            body = (r.get("approved_change") or "").strip()
            note = (r.get("rationale") or "").strip()
            parts.append(f"--- override_id={oid} error_type={et} ---")
            parts.append(body)
            if note:
                parts.append(f"(rationale: {note})")
            parts.append("")
        return "\n".join(parts).strip()

    for gi, cluster in enumerate(clusters, 1):
        parts.append(f"### Group {gi} (merge these into one rule)")
        for oid, text in cluster:
            parts.append(f"- (override #{oid}) {text}")
        parts.append("")

    parts.append("## Override metadata (error_type; for context only)")
    for r in rows:
        oid = r.get("id")
        et = r.get("error_type") or ""
        note = (r.get("rationale") or "").strip()
        line = f"- override #{oid}: {et}"
        if note:
            line += f" | prior rationale: {note[:200]}{'...' if len(note) > 200 else ''}"
        parts.append(line)

    return "\n".join(parts).strip()


async def _consolidator_llm(
    messages: list[dict[str, str]],
    *,
    llm_profile: ResolvedLlmProfile | None = None,
) -> str:
    """Single LLM call. Tries json_schema -> json_object -> plain completion."""
    base_kwargs = dict(
        temperature=LLM_TEMPERATURE,
        model=None if llm_profile else LLM_ANALYZER_MODEL,
        timeout=float(ANALYZER_LLM_TIMEOUT_SECONDS),
        max_retries=0,
        resolved=llm_profile,
    )
    try:
        return await achat(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": _CONSOLIDATOR_JSON_SCHEMA,
            },
            **base_kwargs,
        )
    except Exception as exc:
        _log.warning(
            "consolidator json_schema mode failed (%s); falling back to json_object",
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
            "consolidator json_object mode failed (%s); falling back to plain completion",
            exc,
        )
    return await achat(messages, **base_kwargs)


@dataclass
class ConsolidateMergeResult:
    merged_rule: str
    rationale: str
    model: str
    raw_text: str


def _validate_consolidator_output(raw: str) -> ConsolidatorOutput:
    cleaned = _strip_json_fences(raw)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationError.from_exception_data(
            "ConsolidatorOutput",
            [
                {
                    "type": "json_invalid",
                    "loc": ("root",),
                    "msg": f"Consolidator returned non-JSON: {exc.msg}",
                    "input": cleaned[:200],
                    "ctx": {"error": str(exc)},
                }
            ],
        ) from exc
    return ConsolidatorOutput.model_validate(payload)


def _normalize_merged_text(merged: str) -> str:
    """Turn literal \\n sequences from JSON into real newlines for storage."""
    return (merged or "").replace("\\n", "\n").strip()


async def merge_active_overrides_async(
    active_rows: list[dict[str, Any]],
    *,
    llm_profile: ResolvedLlmProfile | None = None,
) -> ConsolidateMergeResult:
    """One LLM call (with up to one retry on validation failure) merging
    ``approved_change`` texts from the hydrated override dicts."""
    if not active_rows:
        raise ValueError("active_rows must not be empty")

    model_label = (
        llm_profile.default_model if llm_profile is not None else LLM_ANALYZER_MODEL
    )
    user = build_consolidator_user_message(active_rows)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": f"Synthesize the active rules into one JSON object as specified:\n\n{user}",
        },
    ]

    last_error: Exception | None = None
    raw = ""
    for attempt in range(_CONSOLIDATOR_LLM_ATTEMPTS):
        try:
            raw = await _consolidator_llm(messages, llm_profile=llm_profile)
            parsed = _validate_consolidator_output(raw)
            merged = _normalize_merged_text(parsed.merged_rule)
            if not merged:
                raise ValidationError.from_exception_data(
                    "ConsolidatorOutput",
                    [
                        {
                            "type": "value_error",
                            "loc": ("merged_rule",),
                            "msg": "merged_rule must not be empty",
                            "input": parsed.merged_rule,
                            "ctx": {"error": "empty"},
                        }
                    ],
                )
            rationale = (parsed.rationale or "").strip().replace("\\n", "\n")
            return ConsolidateMergeResult(
                merged_rule=merged,
                rationale=rationale or "Merged from active overrides.",
                model=model_label,
                raw_text=raw,
            )
        except ValidationError as exc:
            last_error = exc
            _log.warning(
                "consolidator attempt %d failed validation: %s", attempt + 1, exc
            )
            if attempt >= _CONSOLIDATOR_LLM_ATTEMPTS - 1:
                break
            messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Your last response failed schema validation:\n"
                        f"{exc}\n"
                        "Return ONLY one JSON object {merged_rule, rationale}. "
                        "No prose, no markdown fences, no raw newlines inside string values."
                    ),
                }
            ]
            continue
        except Exception as exc:
            last_error = exc
            _log.warning("consolidator attempt %d errored: %s", attempt + 1, exc)
            break
    raise RuntimeError(f"Consolidator failed: {last_error}")
