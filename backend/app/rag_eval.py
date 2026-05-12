"""RAG / chat batch evaluation: test cases, CSV/JSON loaders, assertions, async runner.

Used by admin API jobs and by the test_rag CLI (HTTP mode imports helpers from here)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Union

# Each entry: plain string (must appear) or list of strings (any one must appear).
ResponseTokenSpec = Union[str, List[str]]

MAX_CSV_ROWS = 200
MAX_SUITE_UPLOAD_BYTES = 2_000_000

TEST_OUTPUT_DIR = Path("tests")
TEST_RESULTS_DIR = TEST_OUTPUT_DIR / "results"
TEST_SUITES_DIR = TEST_OUTPUT_DIR / "suites"


@dataclass
class TestCase:
    id: str
    category: str
    message: str
    expected_ticket_created: bool | None = None
    expected_category: str | None = None
    expected_priority: str | None = None
    expected_category_any: list[str] | None = None
    expected_priority_any: list[str] | None = None
    expected_in_response: list[ResponseTokenSpec] | None = None


def normalize_answer_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def response_matches_token(text_norm: str, token: str) -> bool:
    if not token:
        return True
    t_raw = str(token).strip().lower()
    if t_raw in text_norm:
        return True
    compact_text = re.sub(r"\s+", "", text_norm)
    compact_tok = re.sub(r"\s+", "", t_raw)
    if compact_tok and compact_tok in compact_text:
        return True
    digits_t = digits_only(t_raw)
    if len(digits_t) >= 4:
        d_text = digits_only(text_norm)
        if digits_t in d_text:
            return True
        if digits_t.startswith("0") and len(digits_t) >= 8:
            stripped = digits_t.lstrip("0") or digits_t
            if len(stripped) >= 8 and stripped in d_text:
                return True
    return False


def response_meets_token_spec(text_norm: str, spec: ResponseTokenSpec) -> bool:
    if isinstance(spec, str):
        return response_matches_token(text_norm, spec)
    return any(response_matches_token(text_norm, alt) for alt in spec if alt)


def coerce_expected_in_response(raw: Any) -> list[ResponseTokenSpec] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, list):
        return None
    specs: list[ResponseTokenSpec] = []
    for item in raw:
        if isinstance(item, str):
            specs.append(item)
        elif isinstance(item, list):
            alts = [str(x).strip() for x in item if str(x).strip()]
            if alts:
                specs.append(alts)
        else:
            specs.append(str(item))
    return specs or None


def coerce_str_list(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else None
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out or None
    return None


def parse_expected_in_response_csv(cell: str) -> list[ResponseTokenSpec] | None:
    """CSV cell: `;` separates AND-slots; `|` inside a slot means OR alternatives."""
    cell = (cell or "").strip()
    if not cell:
        return None
    specs: list[ResponseTokenSpec] = []
    for slot in cell.split(";"):
        slot = slot.strip()
        if not slot:
            continue
        if "|" in slot:
            alts = [a.strip() for a in slot.split("|") if a.strip()]
            if not alts:
                continue
            specs.append(alts if len(alts) > 1 else alts[0])
        else:
            specs.append(slot)
    return specs or None


def _parse_bool_cell(raw: str | None) -> bool | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n"}:
        return False
    return None


def build_builtin_cases() -> list[TestCase]:
    return [
        TestCase(
            id="info-1",
            category="informational",
            message="What is the emergency evacuation procedure for building A?",
            expected_ticket_created=False,
        ),
        TestCase(
            id="info-2",
            category="informational",
            message="Where is visitor parking and what are the rules?",
            expected_ticket_created=False,
        ),
        TestCase(
            id="info-3",
            category="informational",
            message="What are the office opening hours on Fridays?",
            expected_ticket_created=False,
        ),
        TestCase(
            id="maint-1",
            category="maintenance",
            message="The AC on floor 2 is not cooling and people are overheating.",
            expected_ticket_created=True,
            expected_category="HVAC",
            expected_priority="HIGH",
        ),
        TestCase(
            id="maint-2",
            category="maintenance",
            message="Water is leaking from the ceiling in room 104 near electrical lights.",
            expected_ticket_created=True,
            expected_category="Plumbing",
            expected_priority="URGENT",
        ),
        TestCase(
            id="maint-3",
            category="maintenance",
            message="Power outlet in conference room C sparks when used.",
            expected_ticket_created=True,
            expected_category="Electrical",
            expected_priority="HIGH",
        ),
        TestCase(
            id="edge-1",
            category="edge",
            message="Something feels off in the office, not sure what exactly.",
            expected_ticket_created=None,
        ),
        TestCase(
            id="edge-2",
            category="edge",
            message="Can you check if the building is okay? We heard a weird noise.",
            expected_ticket_created=None,
        ),
        TestCase(
            id="edge-3",
            category="edge",
            message="I think the air is weird maybe HVAC maybe nothing.",
            expected_ticket_created=None,
        ),
    ]


def build_test_cases_from_json_obj(data: dict[str, Any]) -> list[TestCase]:
    groups = data.get("groups", [])
    out: list[TestCase] = []
    for group in groups:
        group_name = str(group.get("group", "unknown")).strip() or "unknown"
        tests = group.get("tests", [])
        for item in tests:
            out.append(
                TestCase(
                    id=str(item.get("id", f"{group_name}-unknown")),
                    category=group_name,
                    message=str(item.get("message", "")),
                    expected_ticket_created=item.get("should_create_ticket", None),
                    expected_category=item.get("expected_category", None),
                    expected_priority=item.get("expected_priority", None),
                    expected_category_any=coerce_str_list(item.get("expected_category_any")),
                    expected_priority_any=coerce_str_list(item.get("expected_priority_any")),
                    expected_in_response=coerce_expected_in_response(
                        item.get("expected_in_response")
                    ),
                )
            )
    return out


def build_test_cases_from_json_bytes(raw: bytes) -> list[TestCase]:
    if len(raw) > MAX_SUITE_UPLOAD_BYTES:
        raise ValueError(f"JSON suite exceeds max size ({MAX_SUITE_UPLOAD_BYTES} bytes)")
    text = raw.decode("utf-8-sig")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON suite root must be an object")
    return build_test_cases_from_json_obj(data)


def build_test_cases_from_json_path(path: str) -> list[TestCase]:
    p = resolve_existing_path(path)
    return build_test_cases_from_json_obj(
        json.loads(p.read_text(encoding="utf-8"))
    )


def build_test_cases_from_csv_bytes(raw: bytes) -> list[TestCase]:
    if len(raw) > MAX_SUITE_UPLOAD_BYTES:
        raise ValueError(f"CSV suite exceeds max size ({MAX_SUITE_UPLOAD_BYTES} bytes)")
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    fieldnames = {h.strip().lower(): h for h in reader.fieldnames if h}

    def col(*names: str) -> str | None:
        for n in names:
            key = n.lower()
            if key in fieldnames:
                return fieldnames[key]
        return None

    id_col = col("id", "case_id")
    msg_col = col("message", "question", "input")
    if not id_col or not msg_col:
        raise ValueError("CSV must include id and message (or question / input) columns")

    ticket_col = col("should_create_ticket", "create_ticket")
    cat_col = col("expected_category", "category")
    pri_col = col("expected_priority", "priority")
    cat_any_col = col("expected_category_any")
    pri_any_col = col("expected_priority_any")
    resp_tok_col = col("expected_in_response")
    group_col = col("group", "category_group")

    out: list[TestCase] = []
    for row in reader:
        cid = (row.get(id_col) or "").strip()
        message = (row.get(msg_col) or "").strip()
        if not message:
            continue
        if not cid:
            cid = f"row-{len(out) + 1}"
        group_name = "csv"
        if group_col:
            g = (row.get(group_col) or "").strip()
            if g:
                group_name = g

        st_raw = row.get(ticket_col) if ticket_col else None
        expected_ticket = _parse_bool_cell(str(st_raw) if st_raw is not None else None)

        def split_pipe(s: str | None) -> list[str] | None:
            if not s or not str(s).strip():
                return None
            parts = [p.strip() for p in str(s).split("|") if p.strip()]
            return parts or None

        cat_any = split_pipe(row.get(cat_any_col)) if cat_any_col else None
        pri_any = split_pipe(row.get(pri_any_col)) if pri_any_col else None
        exp_cat = (row.get(cat_col) or "").strip() if cat_col else ""
        exp_pri = (row.get(pri_col) or "").strip() if pri_col else ""
        tok_cell = (row.get(resp_tok_col) or "").strip() if resp_tok_col else ""

        out.append(
            TestCase(
                id=cid,
                category=group_name,
                message=message,
                expected_ticket_created=expected_ticket,
                expected_category=exp_cat or None,
                expected_priority=exp_pri or None,
                expected_category_any=cat_any,
                expected_priority_any=pri_any,
                expected_in_response=parse_expected_in_response_csv(tok_cell),
            )
        )

    if len(out) > MAX_CSV_ROWS:
        raise ValueError(f"CSV has more than {MAX_CSV_ROWS} data rows")
    return out


def resolve_existing_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    if candidate.is_absolute():
        return candidate
    for base in (TEST_RESULTS_DIR, TEST_SUITES_DIR, TEST_OUTPUT_DIR):
        alt = base / candidate
        if alt.exists():
            return alt
        by_name = base / candidate.name
        if by_name.exists():
            return by_name
        target_phrase = re.sub(r"\s+", " ", candidate.stem.lower().replace("_", " ")).strip()
        target_tokens = set(re.findall(r"[a-z0-9]+", target_phrase))
        if not target_tokens and not target_phrase:
            continue
        matches: list[Path] = []
        for entry in base.glob(f"*{candidate.suffix}"):
            entry_phrase = re.sub(r"\s+", " ", entry.stem.lower()).strip()
            entry_tokens = set(re.findall(r"[a-z0-9]+", entry_phrase))
            if target_phrase and target_phrase in entry_phrase:
                matches.append(entry)
                continue
            if target_tokens and target_tokens.issubset(entry_tokens):
                matches.append(entry)
        if matches:
            matches.sort(
                key=lambda p: (
                    target_phrase in re.sub(r"\s+", " ", p.stem.lower()).strip(),
                    p.stat().st_mtime,
                ),
                reverse=True,
            )
            return matches[0]
    return candidate


def parse_case_ids_blob(blob: str) -> set[str]:
    parts = re.split(r"[\s,;]+", (blob or "").strip())
    return {p.strip() for p in parts if p.strip()}


def evaluate_case(case: TestCase, response: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    actual_ticket = bool(response.get("ticket_created"))
    actual_category = str(response.get("category", ""))
    actual_priority = str(response.get("priority", ""))

    if case.expected_ticket_created is not None and actual_ticket != case.expected_ticket_created:
        failures.append(
            f"ticket_created expected={case.expected_ticket_created} actual={actual_ticket}"
        )
    if case.expected_category_any:
        if actual_category not in case.expected_category_any:
            failures.append(
                f"category expected one of={case.expected_category_any} actual={actual_category}"
            )
    elif case.expected_category and actual_category != case.expected_category:
        failures.append(
            f"category expected={case.expected_category} actual={actual_category}"
        )
    if case.expected_priority_any:
        if actual_priority not in case.expected_priority_any:
            failures.append(
                f"priority expected one of={case.expected_priority_any} actual={actual_priority}"
            )
    elif case.expected_priority and actual_priority != case.expected_priority:
        failures.append(
            f"priority expected={case.expected_priority} actual={actual_priority}"
        )
    if case.expected_in_response:
        text = normalize_answer_text(str(response.get("response", "")))
        missing: list[str] = []
        for spec in case.expected_in_response:
            if not response_meets_token_spec(text, spec):
                if isinstance(spec, list):
                    missing.append("(" + " | ".join(spec) + ")")
                else:
                    missing.append(str(spec))
        if missing:
            failures.append(f"response missing tokens={missing}")

    return (len(failures) == 0, failures)


def classify_failures(failures: list[str]) -> list[str]:
    kinds: list[str] = []
    for f in failures:
        if "timed out" in f.lower():
            kinds.append("timeout")
        elif "429" in f or "Too Many Requests" in f:
            kinds.append("rate_limit")
        elif "request_error=" in f:
            kinds.append("request_error")
        else:
            kinds.append("logic_mismatch")
    return sorted(set(kinds))


def build_diff(
    previous_results: list[dict[str, Any]], current_results: list[dict[str, Any]]
) -> dict[str, list[str]]:
    prev = {str(r.get("id")): bool(r.get("pass")) for r in previous_results}
    curr = {str(r.get("id")): bool(r.get("pass")) for r in current_results}
    improved: list[str] = []
    regressed: list[str] = []
    still_failed: list[str] = []
    for cid, now_ok in curr.items():
        if cid not in prev:
            continue
        was_ok = prev[cid]
        if (not was_ok) and now_ok:
            improved.append(cid)
        elif was_ok and (not now_ok):
            regressed.append(cid)
        elif (not was_ok) and (not now_ok):
            still_failed.append(cid)
    return {
        "improved": sorted(improved),
        "regressed": sorted(regressed),
        "still_failed": sorted(still_failed),
    }


async def call_chat_with_retry_async(
    invoke: Callable[[], Awaitable[dict[str, Any]]],
    case_id: str,
    *,
    max_retries: int,
    retry_wait_seconds: int,
) -> tuple[dict[str, Any], int]:
    retries_used = 0
    while True:
        try:
            return (await invoke(), retries_used)
        except Exception as exc:
            msg = str(exc)
            is_429 = (
                ("HTTP 429" in msg)
                or ("Too Many Requests" in msg)
                or ("status': 429" in msg)
                or (" 429 " in msg)
            )
            if is_429 and retries_used < max_retries:
                retries_used += 1
                await asyncio.sleep(float(retry_wait_seconds))
                continue
            raise


def _error_response_payload(exc: BaseException) -> dict[str, Any]:
    return {
        "ticket_created": None,
        "ticket_id": None,
        "category": None,
        "priority": None,
        "issue_summary": None,
        "response": "",
        "query_type": None,
        "error": str(exc),
    }


async def run_suite_internal(
    cases: list[TestCase],
    user: dict,
    *,
    run_id: str,
    source_ref: str,
    sleep_between_seconds: float,
    max_retries: int,
    retry_wait_seconds: int,
    per_request_timeout: float | None,
    on_progress: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .main import ChatRequest, run_chat_core

    results: list[dict[str, Any]] = []
    passed = 0
    rate_limit_hits = 0
    total_retries = 0
    api_ok_count = 0
    api_error_count = 0
    api_ok_passed = 0
    loop = asyncio.get_running_loop()
    start_ts = loop.time()

    for idx, case in enumerate(cases):
        response: dict[str, Any]
        ok = False
        failures: list[str]
        retries_used = 0
        try:

            async def invoke() -> dict[str, Any]:
                req = ChatRequest(
                    message=case.message,
                    history=[],
                    run_id=run_id,
                    source_type="test_case",
                    source_id=case.id,
                    source_ref=source_ref,
                )
                if per_request_timeout and per_request_timeout > 0:
                    return await asyncio.wait_for(
                        run_chat_core(req, user, isolate_history=True),
                        timeout=per_request_timeout,
                    )
                return await run_chat_core(req, user, isolate_history=True)

            response, retries_used = await call_chat_with_retry_async(
                invoke,
                case.id,
                max_retries=max_retries,
                retry_wait_seconds=retry_wait_seconds,
            )
            if retries_used > 0:
                rate_limit_hits += 1
                total_retries += retries_used
            ok, failures = evaluate_case(case, response)
            api_ok = True
        except asyncio.TimeoutError:
            response = _error_response_payload(
                TimeoutError(f"timeout after {per_request_timeout}s")
            )
            failures = [f"request_error=timeout after {per_request_timeout}s"]
            api_ok = False
        except Exception as exc:
            response = _error_response_payload(exc)
            failures = [f"request_error={exc}"]
            if ("HTTP 429" in str(exc)) or ("Too Many Requests" in str(exc)):
                rate_limit_hits += 1
            api_ok = False
        if ok:
            passed += 1
        if api_ok:
            api_ok_count += 1
            if ok:
                api_ok_passed += 1
        else:
            api_error_count += 1

        fail_types = classify_failures(failures)
        processed = idx + 1
        row = {
            "id": case.id,
            "category": case.category,
            "message": case.message,
            "expected": {
                "ticket_created": case.expected_ticket_created,
                "category": case.expected_category,
                "priority": case.expected_priority,
                "category_any": case.expected_category_any,
                "priority_any": case.expected_priority_any,
            },
            "actual": {
                "ticket_created": response.get("ticket_created"),
                "ticket_id": response.get("ticket_id"),
                "category": response.get("category"),
                "priority": response.get("priority"),
                "issue_summary": response.get("issue_summary"),
                "response": response.get("response"),
                "query_type": response.get("query_type"),
            },
            "pass": ok,
            "failures": failures,
            "rate_limit_retries_used": retries_used,
            "api_ok": api_ok,
            "failure_types": fail_types,
            "processed_index": processed,
        }
        results.append(row)
        if on_progress:
            await on_progress(list(results))

        if idx < len(cases) - 1 and sleep_between_seconds > 0:
            await asyncio.sleep(float(sleep_between_seconds))

    total = len(cases)
    failed = total - passed
    elapsed = loop.time() - start_ts
    summary = {
        "mode": "internal",
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
        "api_ok_count": api_ok_count,
        "api_error_count": api_error_count,
        "api_ok_passed": api_ok_passed,
        "api_ok_failed": max(0, api_ok_count - api_ok_passed),
        "api_ok_pass_rate": round((api_ok_passed / api_ok_count) * 100, 2)
        if api_ok_count
        else 0.0,
        "rate_limit_hits": rate_limit_hits,
        "rate_limit_retries_total": total_retries,
        "sleep_between_seconds": sleep_between_seconds,
        "per_request_timeout_seconds": per_request_timeout,
        "max_retries": max_retries,
        "retry_wait_seconds": retry_wait_seconds,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
    }
    return results, summary


def merge_report(
    *,
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    user: dict[str, Any] | None,
    compare_prev_results: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    diff = None
    if compare_prev_results is not None:
        diff = build_diff(compare_prev_results, results)
    out_user = dict(user) if user else {}
    summary_out = {**summary, "user": out_user}
    return {
        "summary": summary_out,
        "lists": {
            "failed_all_case_ids_file": "",
            "failed_api_ok_case_ids_file": "",
            "failed_api_error_case_ids_file": "",
            "failed_all_case_ids_count": len(
                [r for r in results if not bool(r.get("pass"))]
            ),
            "failed_api_ok_case_ids_count": len(
                [
                    r
                    for r in results
                    if (not bool(r.get("pass"))) and bool(r.get("api_ok"))
                ]
            ),
            "failed_api_error_case_ids_count": len(
                [
                    r
                    for r in results
                    if (not bool(r.get("pass"))) and (not bool(r.get("api_ok")))
                ]
            ),
        },
        "diff": diff,
        "results": results,
    }


def check_api_ok_gates(
    summary: dict[str, Any],
    *,
    min_api_ok_pass_rate: float | None,
    min_api_ok_count: int,
) -> tuple[bool, str | None]:
    if min_api_ok_count > 0:
        if summary["api_ok_count"] < min_api_ok_count:
            return (
                False,
                f"api_ok_count={summary['api_ok_count']} < min_api_ok_count={min_api_ok_count}",
            )
    if min_api_ok_pass_rate is not None:
        if summary["api_ok_count"] < 1:
            return (False, "no api_ok responses; cannot verify min_api_ok_pass_rate")
        if summary["api_ok_pass_rate"] < min_api_ok_pass_rate:
            return (
                False,
                f"api_ok_pass_rate={summary['api_ok_pass_rate']}% < "
                f"min_api_ok_pass_rate={min_api_ok_pass_rate}",
            )
    return (True, None)
