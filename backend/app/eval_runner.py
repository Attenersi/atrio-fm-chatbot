"""Faza C: in-process eval runner used by /api/admin/training-quality/eval/*.

Calls the same backend pieces a real chat would (rag.retrieve_with_sources +
rag.agenerate + classifier.parse_llm_json), but skips HTTP, slowapi and chat
history so it doesn't compete with live traffic for the per-user limits.

The NVIDIA RPM token bucket from llm.py is shared, so eval_runner cannot
exceed the global LLM budget regardless of concurrency."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .rag_eval import (
    ResponseTokenSpec,
    TestCase,
    coerce_expected_in_response,
    coerce_str_list,
    evaluate_case,
)
from .classifier import fallback_response, parse_llm_json
from .rag import agenerate, effective_rag_top_k, retrieve_with_sources


_log = logging.getLogger("fm.eval")


@dataclass
class EvalCase:
    id: str
    message: str
    expected_category: str | None = None
    expected_priority: str | None = None
    expected_ticket_created: bool | None = None
    expected_category_any: list[str] | None = None
    expected_priority_any: list[str] | None = None
    expected_in_response: list[ResponseTokenSpec] | None = None

    def to_test_case(self) -> TestCase:
        return TestCase(
            id=self.id,
            category="golden",
            message=self.message,
            expected_ticket_created=self.expected_ticket_created,
            expected_category=self.expected_category,
            expected_priority=self.expected_priority,
            expected_category_any=self.expected_category_any,
            expected_priority_any=self.expected_priority_any,
            expected_in_response=self.expected_in_response,
        )


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    actual: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    error: str | None = None


@dataclass
class EvalSummary:
    total: int
    passed: int
    accuracy_overall: float
    accuracy_category: float | None
    accuracy_priority: float | None
    accuracy_ticket_created: float | None
    accuracy_response_tokens: float | None
    elapsed_seconds: float
    results: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Cast CaseResult dicts already converted by asdict.
        return d


def load_golden(path: str | Path) -> list[EvalCase]:
    """Load JSONL of golden cases. See data/eval_golden.jsonl format."""
    p = Path(path)
    cases: list[EvalCase] = []
    if not p.exists():
        return cases
    for line_no, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            _log.exception("eval_golden line %d JSON parse failed", line_no)
            continue
        cases.append(
            EvalCase(
                id=str(d.get("id") or f"line-{line_no}"),
                message=str(d.get("message") or "").strip(),
                expected_category=d.get("expected_category"),
                expected_priority=d.get("expected_priority"),
                expected_ticket_created=d.get("expected_ticket_created"),
                expected_category_any=coerce_str_list(d.get("expected_category_any")),
                expected_priority_any=coerce_str_list(d.get("expected_priority_any")),
                expected_in_response=coerce_expected_in_response(d.get("expected_in_response")),
            )
        )
    return [c for c in cases if c.message]


async def _run_one(case: EvalCase) -> CaseResult:
    started = time.monotonic()
    try:
        # Same call pattern as api_chat: retrieval is sync (Chroma), so push
        # it to a worker thread; LLM call is async.
        context, _sources = await asyncio.to_thread(
            retrieve_with_sources, case.message, effective_rag_top_k()
        )
        raw = await agenerate(case.message, context, history=None)
        try:
            payload = parse_llm_json(raw)
        except Exception:
            payload = fallback_response(raw)
        actual = {
            "category": str(payload.get("category", "")),
            "priority": str(payload.get("priority", "")),
            "ticket_created": str(payload.get("create_ticket", "NO")).upper() == "YES",
            "response": str(payload.get("response", "")),
            "issue_summary": str(payload.get("issue_summary", "")),
        }
        passed, failures = evaluate_case(case.to_test_case(), actual)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return CaseResult(
            case_id=case.id, passed=passed, failures=failures, actual=actual, elapsed_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _log.exception("eval case %s crashed", case.id)
        return CaseResult(
            case_id=case.id, passed=False, failures=[f"crash: {exc}"], actual={},
            elapsed_ms=elapsed_ms, error=str(exc),
        )


async def run_eval(
    cases: Iterable[EvalCase],
    *,
    max_concurrency: int = 8,
    progress_cb=None,
) -> EvalSummary:
    """Run all cases concurrently (bounded by `max_concurrency` and the global
    NVIDIA RPM bucket from llm.py). Returns per-case + aggregate stats."""
    cases_list = list(cases)
    if not cases_list:
        return EvalSummary(0, 0, 0.0, None, None, None, None, 0.0, [])

    sem = asyncio.Semaphore(max(1, int(max_concurrency)))
    results: list[CaseResult] = []
    started_at = time.monotonic()

    async def runner(case: EvalCase) -> CaseResult:
        async with sem:
            res = await _run_one(case)
            if progress_cb is not None:
                try:
                    progress_cb(len(results) + 1, len(cases_list))
                except Exception:
                    _log.exception("eval progress_cb failed")
            results.append(res)
            return res

    await asyncio.gather(*(runner(c) for c in cases_list))
    # Restore original order (gather already preserves but just in case).
    by_id = {r.case_id: r for r in results}
    ordered = [by_id[c.id] for c in cases_list if c.id in by_id]

    # Per-field accuracy (only count cases that have an expected value for the field).
    def field_acc(fname: str) -> float | None:
        relevant = 0
        ok = 0
        for c, r in zip(cases_list, ordered):
            failure_marker = None
            if fname == "category":
                if c.expected_category is None and not c.expected_category_any:
                    continue
                failure_marker = "category"
            elif fname == "priority":
                if c.expected_priority is None and not c.expected_priority_any:
                    continue
                failure_marker = "priority"
            elif fname == "ticket_created":
                if c.expected_ticket_created is None:
                    continue
                failure_marker = "ticket_created"
            elif fname == "response_tokens":
                if not c.expected_in_response:
                    continue
                failure_marker = "response missing tokens"
            relevant += 1
            if r.error:
                continue
            if not any(failure_marker in f for f in r.failures):
                ok += 1
        return (ok / relevant) if relevant > 0 else None

    passed = sum(1 for r in ordered if r.passed)
    elapsed = time.monotonic() - started_at
    return EvalSummary(
        total=len(ordered),
        passed=passed,
        accuracy_overall=passed / len(ordered) if ordered else 0.0,
        accuracy_category=field_acc("category"),
        accuracy_priority=field_acc("priority"),
        accuracy_ticket_created=field_acc("ticket_created"),
        accuracy_response_tokens=field_acc("response_tokens"),
        elapsed_seconds=round(elapsed, 2),
        results=ordered,
    )
