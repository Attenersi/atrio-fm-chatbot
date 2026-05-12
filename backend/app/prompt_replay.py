"""Mini-replay for prompt overrides.

After a reviewer applies (or wants to test) a prompt override, we replay a
small set of inputs through the live chat pipeline (`rag.agenerate`) so the
admin can see whether the rule fixes the originally flagged cases without
breaking similar ones. Each replay item is also persisted into
`training_examples` (source_type='prompt_replay') so it naturally enters the
normal review queue and the feedback loop can continue.

Per replay request we issue at most:
- 1 LLM call per affected input to generate K paraphrases (one batched call,
  not K calls), and
- 1 LLM call per question (original + paraphrases) for `rag.agenerate`.

All LLM calls share the global RPM bucket from `llm.py`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from .classifier import fallback_response, parse_llm_json
from .config import (
    LLM_ANALYZER_MODEL,
    LLM_TEMPERATURE,
    REPLAY_DEFAULT_MAX_INPUTS,
    REPLAY_DEFAULT_PARAPHRASES,
)
from .database import (
    create_training_example,
    get_prompt_override,
    get_training_example,
)
from .llm import achat
from .llm_profiles import ResolvedLlmProfile
from .rag import agenerate, effective_rag_top_k, retrieve_with_sources


def predicted_replay_call_count(max_inputs: int, paraphrases_per_input: int) -> int:
    """How many LLM calls a replay run will issue against the global RPM bucket.

    For each affected input we run:
      - 1 paraphrase-generation call (skipped only if paraphrases==0), and
      - (1 + paraphrases_per_input) chat calls (one for the original, one
        per paraphrase).

    We use this for pre-flight rejection in the API handler so a single
    replay cannot accidentally drain the entire LLM_RPM_BUDGET.
    """
    n = max(0, int(max_inputs))
    k = max(0, int(paraphrases_per_input))
    paraphrase_calls = n if k > 0 else 0
    return paraphrase_calls + n * (1 + k)


_log = logging.getLogger("fm.replay")


DEFAULT_MAX_INPUTS = REPLAY_DEFAULT_MAX_INPUTS
DEFAULT_PARAPHRASES = REPLAY_DEFAULT_PARAPHRASES


@dataclass
class ReplayItemResult:
    """Outcome of running one question through the live pipeline."""

    input_text: str
    is_paraphrase: bool
    seed_example_id: int | None
    actual_output: dict[str, Any]
    expected_output: dict[str, Any]
    matches_expected: bool
    mismatch_fields: list[str]
    training_example_id: int | None = None


@dataclass
class ReplaySummary:
    override_id: int
    total_original: int
    passed_original: int
    total_paraphrases: int
    passed_paraphrases: int
    examples_logged: int
    items: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "override_id": self.override_id,
            "total_original": self.total_original,
            "passed_original": self.passed_original,
            "total_paraphrases": self.total_paraphrases,
            "passed_paraphrases": self.passed_paraphrases,
            "examples_logged": self.examples_logged,
            "items": self.items,
        }


_PARAPHRASE_SYSTEM_PROMPT = """You are a paraphrase generator for Facility Management chatbot test inputs.

Given one user message, produce K alternative messages that:
- ask about the same underlying issue / topic / classification,
- vary wording, tone, or phrasing (formal vs casual, longer vs shorter),
- keep the same severity signals (do not invent danger words; do not remove safety
  signals like "smoke", "leak", "sparks" if present),
- stay realistic for a tenant or staff member to write,
- are in the same language as the source message.

Return STRICT JSON ONLY: {"paraphrases": ["...", "..."]}. Exactly K entries.
"""


def _compare_classification(
    actual: dict[str, Any], expected: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Compare two chatbot outputs on classification fields. Strings are
    compared case-insensitively. ticket_created is normalized YES/NO ↔ bool."""
    if not isinstance(expected, dict) or not expected:
        return True, []

    mismatches: list[str] = []

    def _norm(v: Any) -> str:
        return str(v or "").strip().upper()

    def _norm_bool(v: Any) -> str:
        s = str(v or "").strip().upper()
        if s in {"YES", "TRUE", "1"}:
            return "YES"
        if s in {"NO", "FALSE", "0"}:
            return "NO"
        if isinstance(v, bool):
            return "YES" if v else "NO"
        return s

    if "category" in expected and _norm(expected.get("category")):
        if _norm(actual.get("category")) != _norm(expected.get("category")):
            mismatches.append("category")
    if "priority" in expected and _norm(expected.get("priority")):
        if _norm(actual.get("priority")) != _norm(expected.get("priority")):
            mismatches.append("priority")
    if "create_ticket" in expected:
        if _norm_bool(actual.get("create_ticket")) != _norm_bool(
            expected.get("create_ticket")
        ):
            mismatches.append("create_ticket")
    return (len(mismatches) == 0), mismatches


async def _generate_paraphrases(
    text: str, k: int, *, llm_profile: ResolvedLlmProfile | None = None
) -> list[str]:
    """Single LLM call to produce K paraphrases of `text`. On failure, returns
    an empty list (we will simply skip paraphrase replay for that input)."""
    if k <= 0 or not text.strip():
        return []
    user = (
        f"Source message (language: keep the same):\n{text.strip()}\n\n"
        f"Produce exactly K={k} paraphrases. Return JSON only."
    )
    messages = [
        {"role": "system", "content": _PARAPHRASE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        raw = await achat(
            messages,
            temperature=LLM_TEMPERATURE,
            model=None if llm_profile else LLM_ANALYZER_MODEL,
            resolved=llm_profile,
        )
    except Exception as exc:
        _log.warning("paraphrase call failed: %s", exc)
        return []
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            _log.warning("paraphrase JSON unparseable: %s", cleaned[:200])
            return []
        try:
            data = json.loads(cleaned[start : end + 1])
        except Exception:
            return []
    items = data.get("paraphrases") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for it in items[:k]:
        s = str(it or "").strip()
        if s and s != text.strip():
            out.append(s)
    return out


async def _run_one(
    text: str, *, llm_profile: ResolvedLlmProfile | None = None
) -> dict[str, Any]:
    """Run a single message through the live pipeline (with active overrides)
    and return the parsed classification dict."""
    context, _sources = await asyncio.to_thread(
        retrieve_with_sources, text, effective_rag_top_k()
    )
    raw = await agenerate(text, context, history=None, resolved=llm_profile)
    try:
        return parse_llm_json(raw)
    except Exception:
        return fallback_response(raw)


def _build_expected_from_seed(seed: dict[str, Any]) -> dict[str, Any]:
    """Pick reviewer's ground truth: prefer ideal_output (set during review),
    fall back to expected_payload (test_case rows)."""
    ideal = seed.get("ideal_output") if isinstance(seed.get("ideal_output"), dict) else {}
    if ideal:
        return ideal
    exp = (
        seed.get("expected_payload") if isinstance(seed.get("expected_payload"), dict) else {}
    )
    return exp or {}


async def stream_replay_for_override(
    override_id: int,
    *,
    max_inputs: int = DEFAULT_MAX_INPUTS,
    paraphrases_per_input: int = DEFAULT_PARAPHRASES,
    log_to_db: bool = True,
    llm_profile: ResolvedLlmProfile | None = None,
):
    """Async-generator variant of :func:`replay_for_override`.

    Yields progress dicts as the run advances. Event shapes:

    - ``{"type": "started", "total_inputs": int, "predicted_calls": int}``
    - ``{"type": "item", "item": <serialized ReplayItemResult>, "index": int,
       "total": int}`` for each completed (seed × paraphrase) tuple
    - ``{"type": "summary", "summary": <ReplaySummary.to_dict()>}`` once

    Consumers that just want the aggregate (HTTP POST handler, tests) can
    use :func:`replay_for_override`, which collapses this generator into a
    single ``ReplaySummary``.
    """
    override = get_prompt_override(int(override_id))
    if not override:
        raise ValueError(f"Override {override_id} not found")

    affected_ids: list[int] = list(override.get("affected_example_ids") or [])
    seeds: list[dict[str, Any]] = []
    for eid in affected_ids[: max(1, int(max_inputs))]:
        seed = get_training_example(int(eid))
        if not seed or not str(seed.get("input_text") or "").strip():
            continue
        seeds.append(seed)

    if not seeds:
        empty = ReplaySummary(
            override_id=int(override_id),
            total_original=0,
            passed_original=0,
            total_paraphrases=0,
            passed_paraphrases=0,
            examples_logged=0,
            items=[],
        )
        yield {"type": "started", "total_inputs": 0, "predicted_calls": 0}
        yield {"type": "summary", "summary": empty.to_dict()}
        return

    predicted = predicted_replay_call_count(len(seeds), paraphrases_per_input)
    yield {
        "type": "started",
        "total_inputs": len(seeds),
        "predicted_calls": predicted,
    }

    paraphrase_tasks = [
        _generate_paraphrases(
            str(seed["input_text"]),
            int(paraphrases_per_input),
            llm_profile=llm_profile,
        )
        for seed in seeds
    ]
    paraphrase_lists = await asyncio.gather(*paraphrase_tasks, return_exceptions=True)

    work: list[tuple[dict[str, Any], str, bool]] = []
    for seed, paraphrases in zip(seeds, paraphrase_lists):
        text = str(seed.get("input_text") or "").strip()
        if text:
            work.append((seed, text, False))
        if isinstance(paraphrases, Exception):
            _log.warning(
                "paraphrase generation crashed for seed %s: %s",
                seed.get("id"),
                paraphrases,
            )
            continue
        for p in paraphrases or []:
            work.append((seed, p, True))

    items: list[ReplayItemResult] = []
    examples_logged = 0
    total_original = 0
    passed_original = 0
    total_paraphrases = 0
    passed_paraphrases = 0

    total_work = len(work)
    for idx, (seed, text, is_paraphrase) in enumerate(work, start=1):
        try:
            actual = await _run_one(text, llm_profile=llm_profile)
        except Exception as exc:
            _log.exception("replay agenerate failed for seed %s", seed.get("id"))
            actual = {
                "category": "General",
                "priority": "NORMAL",
                "department": "Facility Management",
                "create_ticket": "NO",
                "response": f"[replay error: {exc}]",
                "issue_summary": "",
                "in_scope": "YES",
                "grounded": "NO",
                "query_type": "INFORMATIONAL",
            }

        expected = _build_expected_from_seed(seed) if not is_paraphrase else {}
        if is_paraphrase:
            seed_expected = _build_expected_from_seed(seed)
            expected = {
                k: v
                for k, v in seed_expected.items()
                if k in {"category", "priority", "create_ticket"}
            }

        passed, mismatches = _compare_classification(actual, expected)

        if is_paraphrase:
            total_paraphrases += 1
            if passed:
                passed_paraphrases += 1
        else:
            total_original += 1
            if passed:
                passed_original += 1

        item = ReplayItemResult(
            input_text=text,
            is_paraphrase=is_paraphrase,
            seed_example_id=int(seed.get("id") or 0) or None,
            actual_output=actual,
            expected_output=expected,
            matches_expected=passed,
            mismatch_fields=mismatches,
        )
        items.append(item)

        if log_to_db:
            try:
                stored = create_training_example(
                    input_text=text,
                    actual_output=actual,
                    user_id=None,
                    user_role="prompt_replay",
                    query_type=str(actual.get("query_type", "")),
                    in_scope=str(actual.get("in_scope", "")),
                    grounded=str(actual.get("grounded", "")),
                    context_used=[],
                    used_sources=[],
                    context_count=0,
                    ticket_created=str(actual.get("create_ticket", "NO")).upper()
                    == "YES",
                    ticket_id=None,
                    model=LLM_ANALYZER_MODEL,
                    run_id=f"replay:{override_id}",
                    source_type="prompt_replay",
                    source_id=f"override:{override_id}:{'p' if is_paraphrase else 'o'}:{item.seed_example_id or 0}",
                    source_ref=f"override:{override_id}",
                    knowledge_gap_logged=False,
                    knowledge_gap_reason="",
                    mismatch_fields=mismatches,
                    expected_payload=expected,
                    actual_payload=actual,
                    retrieval_meta={},
                )
                if stored:
                    examples_logged += 1
                    item.training_example_id = int(stored.get("id") or 0) or None
            except Exception:
                _log.exception(
                    "create_training_example failed during replay for override %s",
                    override_id,
                )

        yield {
            "type": "item",
            "index": idx,
            "total": total_work,
            "item": {
                "input_text": item.input_text,
                "is_paraphrase": item.is_paraphrase,
                "seed_example_id": item.seed_example_id,
                "actual_output": item.actual_output,
                "expected_output": item.expected_output,
                "matches_expected": item.matches_expected,
                "mismatch_fields": item.mismatch_fields,
                "training_example_id": item.training_example_id,
            },
        }

    summary = ReplaySummary(
        override_id=int(override_id),
        total_original=total_original,
        passed_original=passed_original,
        total_paraphrases=total_paraphrases,
        passed_paraphrases=passed_paraphrases,
        examples_logged=examples_logged,
        items=[
            {
                "input_text": it.input_text,
                "is_paraphrase": it.is_paraphrase,
                "seed_example_id": it.seed_example_id,
                "actual_output": it.actual_output,
                "expected_output": it.expected_output,
                "matches_expected": it.matches_expected,
                "mismatch_fields": it.mismatch_fields,
                "training_example_id": it.training_example_id,
            }
            for it in items
        ],
    )
    yield {"type": "summary", "summary": summary.to_dict()}


async def replay_for_override(
    override_id: int,
    *,
    max_inputs: int = DEFAULT_MAX_INPUTS,
    paraphrases_per_input: int = DEFAULT_PARAPHRASES,
    log_to_db: bool = True,
    llm_profile: ResolvedLlmProfile | None = None,
) -> ReplaySummary:
    """Replay the override on its affected examples + paraphrases of each.

    This is a convenience wrapper around :func:`stream_replay_for_override`
    that drains the generator and returns the final summary, used by the
    legacy POST endpoint and tests. Each result is persisted into
    ``training_examples`` (source_type='prompt_replay') when
    ``log_to_db=True``, so the reviewer can later inspect whether the new
    rule degraded any case.
    """
    summary_dict: dict[str, Any] = {}
    async for event in stream_replay_for_override(
        override_id,
        max_inputs=max_inputs,
        paraphrases_per_input=paraphrases_per_input,
        log_to_db=log_to_db,
        llm_profile=llm_profile,
    ):
        if event.get("type") == "summary":
            summary_dict = event.get("summary") or {}

    return ReplaySummary(
        override_id=int(summary_dict.get("override_id") or override_id),
        total_original=int(summary_dict.get("total_original") or 0),
        passed_original=int(summary_dict.get("passed_original") or 0),
        total_paraphrases=int(summary_dict.get("total_paraphrases") or 0),
        passed_paraphrases=int(summary_dict.get("passed_paraphrases") or 0),
        examples_logged=int(summary_dict.get("examples_logged") or 0),
        items=list(summary_dict.get("items") or []),
    )
