from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

# Each entry: plain string (must appear) or list of strings (any one must appear).
ResponseTokenSpec = str | list[str]
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
    # If set, actual category must be one of these (instead of exact expected_category).
    expected_category_any: list[str] | None = None
    expected_priority_any: list[str] | None = None
    expected_in_response: list[ResponseTokenSpec] | None = None


class Ansi:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"


def _safe_print(text: str) -> None:
    """
    Print helper resilient to Windows cp1250/cp1252 consoles when test messages contain emoji/Unicode.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace unsupported glyphs so the run can continue and still preserve diagnostics.
        safe = text.encode("ascii", errors="replace").decode("ascii")
        print(safe)


def normalize_answer_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def response_matches_token(text_norm: str, token: str) -> bool:
    """
    Match a single expected fragment against normalized assistant text.
    Handles minor formatting variance (spacing) and digit-only substrings (phones, years).
    """
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
    """
    JSON may list plain strings (all required) or inner arrays (alternatives / OR).
    Example: ["always open", ["8 min", "8-minute"]] means both slots must match,
    with the second satisfied by any listed synonym.
    """
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


def build_test_cases() -> list[TestCase]:
    return [
        # Informational (should not create tickets)
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
        # Real maintenance (should create tickets)
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
        # Edge cases (ambiguous)
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


def build_test_cases_from_json(path: str) -> list[TestCase]:
    raw = resolve_existing_path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
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
                    expected_in_response=coerce_expected_in_response(item.get("expected_in_response")),
                )
            )
    return out


def parse_case_ids_file(path: str) -> set[str]:
    rows = resolve_existing_path(path).read_text(encoding="utf-8").splitlines()
    return {row.strip() for row in rows if row.strip()}


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
        # Fuzzy fallback for renamed files like "DD.MM.YYYY, weird top10 cases.json".
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
            # Prefer files that contain the literal phrase over token-only matches.
            matches.sort(
                key=lambda p: (
                    target_phrase in re.sub(r"\s+", " ", p.stem.lower()).strip(),
                    p.stat().st_mtime,
                ),
                reverse=True,
            )
            return matches[0]
    return candidate


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach API at {self.base_url}: {exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response for {path}: {raw}") from exc

    def login(self, username: str, password: str) -> dict[str, Any]:
        return self._post_json("/api/auth/login", {"username": username, "password": password})

    def chat(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        *,
        run_id: str = "",
        source_type: str = "test_case",
        source_id: str = "",
        source_ref: str = "",
    ) -> dict[str, Any]:
        payload = {
            "message": message,
            "history": history or [],
            "run_id": run_id,
            "source_type": source_type,
            "source_id": source_id,
            "source_ref": source_ref,
        }
        return self._post_json("/api/chat", payload)


def call_chat_with_retry(
    client: ApiClient,
    case: TestCase,
    *,
    max_retries: int = 3,
    retry_wait_seconds: int = 10,
    run_id: str = "",
    source_ref: str = "",
) -> tuple[dict[str, Any], int]:
    """
    Returns: (response, rate_limit_retries_used)
    Raises exception if all retries fail or non-429 error occurs.
    """
    retries_used = 0
    attempt = 0
    while True:
        attempt += 1
        try:
            return (
                client.chat(
                    case.message,
                    history=[],
                    run_id=run_id,
                    source_type="test_case",
                    source_id=case.id,
                    source_ref=source_ref,
                ),
                retries_used,
            )
        except Exception as exc:
            msg = str(exc)
            is_429 = ("HTTP 429" in msg) or ("Too Many Requests" in msg) or ("status': 429" in msg)
            if is_429 and retries_used < max_retries:
                retries_used += 1
                print(
                    f"[{case.id}] rate limit hit (429). "
                    f"Retry {retries_used}/{max_retries} in {retry_wait_seconds}s..."
                )
                time.sleep(retry_wait_seconds)
                continue
            raise


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
        if "timed out" in f:
            kinds.append("timeout")
        elif "429" in f or "Too Many Requests" in f:
            kinds.append("rate_limit")
        elif "request_error=" in f:
            kinds.append("request_error")
        else:
            kinds.append("logic_mismatch")
    return sorted(set(kinds))


def compute_eta(start_ts: float, processed: int, total: int) -> tuple[float, float]:
    elapsed = max(0.0, time.time() - start_ts)
    if processed <= 0:
        return elapsed, 0.0
    avg = elapsed / processed
    remaining = max(0, total - processed)
    return elapsed, avg * remaining


def format_seconds(seconds: float) -> str:
    whole = int(max(0, seconds))
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def write_case_id_list(path: Path, case_ids: list[str]) -> None:
    text = "\n".join(case_ids) + ("\n" if case_ids else "")
    path.write_text(text, encoding="utf-8")


def _slug_to_label(value: str) -> str:
    text = re.sub(r"[_\-]+", " ", value.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text or "test run"


def _safe_file_fragment(value: str) -> str:
    # Keep file names portable on Windows/macOS/Linux.
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "test run"


def _default_output_path(args: argparse.Namespace) -> Path:
    now_local = datetime.now()
    date_label = now_local.strftime("%d.%m.%Y")
    if args.run_id.strip():
        desc = _slug_to_label(args.run_id)
    elif args.cases_file.strip():
        desc = _slug_to_label(Path(args.cases_file).stem)
    else:
        desc = "builtin cases"
    filename = f"{date_label}, {_safe_file_fragment(desc)}.json"
    return TEST_RESULTS_DIR / filename


def build_diff(previous_results: list[dict[str, Any]], current_results: list[dict[str, Any]]) -> dict[str, list[str]]:
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run RAG/API chat tests and output pass/fail report."
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--username", default="admin", help="Login username")
    parser.add_argument("--password", default="admin", help="Login password")
    parser.add_argument(
        "--output",
        default="",
        help="Path for JSON results report (default: auto in tests/ with DD.MM.YYYY, description.json)",
    )
    parser.add_argument(
        "--cases-file",
        default="",
        help="Optional path to JSON test suite (e.g. atrio_test_cases.json)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=240,
        help="HTTP timeout per request in seconds (default: 240; raise for slow NVIDIA)",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=15.0,
        help="Delay in seconds between test cases (default: 15.0)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries when a 429 rate-limit response is hit",
    )
    parser.add_argument(
        "--retry-wait",
        type=int,
        default=10,
        help="Seconds to wait before retry after 429",
    )
    parser.add_argument(
        "--case-ids-file",
        default="",
        help="Optional file with case IDs (one per line) to run subset/rerun",
    )
    parser.add_argument(
        "--compare-with",
        default="",
        help="Optional previous results JSON file for improved/regressed/still_failed diff",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run identifier stored with each /api/chat training example",
    )
    args = parser.parse_args()

    client = ApiClient(args.base_url, timeout_seconds=args.timeout)

    print(f"Connecting to {args.base_url} and authenticating as '{args.username}'...")
    login_response = client.login(args.username, args.password)
    user_info = login_response.get("user", {})
    print(f"Authenticated: user={user_info.get('username')} role={user_info.get('role')}")

    if args.cases_file:
        cases = build_test_cases_from_json(args.cases_file)
    else:
        cases = build_test_cases()
    if args.case_ids_file:
        selected_ids = parse_case_ids_file(args.case_ids_file)
        before_count = len(cases)
        cases = [c for c in cases if c.id in selected_ids]
        print(
            f"{Ansi.CYAN}Subset mode: selected {len(cases)}/{before_count} cases from {args.case_ids_file}.{Ansi.RESET}"
        )
    results: list[dict[str, Any]] = []
    passed = 0
    rate_limit_hits = 0
    total_retries = 0
    api_ok_count = 0
    api_error_count = 0
    api_ok_passed = 0
    start_ts = time.time()

    run_id = args.run_id.strip() or datetime.now(timezone.utc).strftime("testrun-%Y%m%dT%H%M%SZ")
    if args.cases_file:
        source_ref = resolve_existing_path(args.cases_file).name
    else:
        source_ref = "builtin_cases"

    for idx, case in enumerate(cases):
        response: dict[str, Any]
        ok = False
        failures: list[str]
        retries_used = 0
        try:
            response, retries_used = call_chat_with_retry(
                client,
                case,
                max_retries=args.max_retries,
                retry_wait_seconds=args.retry_wait,
                run_id=run_id,
                source_ref=source_ref,
            )
            if retries_used > 0:
                rate_limit_hits += 1
                total_retries += retries_used
            ok, failures = evaluate_case(case, response)
            api_ok = True
        except Exception as exc:
            response = {
                "ticket_created": None,
                "ticket_id": None,
                "category": None,
                "priority": None,
                "issue_summary": None,
                "response": "",
                "query_type": None,
            }
            failures = [f"request_error={exc}"]
            if ("HTTP 429" in str(exc)) or ("Too Many Requests" in str(exc)) or ("status': 429" in str(exc)):
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
        elapsed, eta = compute_eta(start_ts, processed, len(cases))
        status_label = "PASSED" if ok else "FAILED"
        status_color = Ansi.GREEN if ok else Ansi.RED

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

        _safe_print("=" * 80)
        _safe_print(
            f"[{processed}/{len(cases)}] "
            f"{status_color}{status_label}{Ansi.RESET} | "
            f"{case.id} | elapsed={format_seconds(elapsed)} | eta={format_seconds(eta)}"
        )
        _safe_print(f"Category: {case.category}")
        _safe_print(f"Message: {case.message}")
        _safe_print(
            "Actual: "
            f"ticket_created={row['actual']['ticket_created']} "
            f"category={row['actual']['category']} "
            f"priority={row['actual']['priority']}"
        )
        _safe_print(f"Issue summary: {row['actual']['issue_summary']}")
        _safe_print(f"Response text: {row['actual']['response']}")
        if failures:
            _safe_print("Checks failed: " + " | ".join(failures))
            _safe_print(f"Failure types: {fail_types}")
        if retries_used:
            _safe_print(f"Rate-limit retries used: {retries_used}")
        if idx < len(cases) - 1 and args.sleep_between > 0:
            time.sleep(args.sleep_between)

    total = len(cases)
    failed = total - passed
    summary = {
        "base_url": args.base_url,
        "user": user_info,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
        "api_ok_count": api_ok_count,
        "api_error_count": api_error_count,
        "api_ok_passed": api_ok_passed,
        "api_ok_failed": max(0, api_ok_count - api_ok_passed),
        "api_ok_pass_rate": round((api_ok_passed / api_ok_count) * 100, 2) if api_ok_count else 0.0,
        "rate_limit_hits": rate_limit_hits,
        "rate_limit_retries_total": total_retries,
        "sleep_between_seconds": args.sleep_between,
        "timeout_seconds": args.timeout,
        "max_retries": args.max_retries,
        "retry_wait_seconds": args.retry_wait,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    failed_all_case_ids = [str(r["id"]) for r in results if not bool(r["pass"])]
    failed_api_ok_case_ids = [str(r["id"]) for r in results if (not bool(r["pass"])) and bool(r["api_ok"])]
    failed_api_error_case_ids = [str(r["id"]) for r in results if (not bool(r["pass"])) and (not bool(r["api_ok"]))]

    if args.output.strip():
        output_path = Path(args.output)
    else:
        output_path = _default_output_path(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stem = output_path.stem
    parent = output_path.parent if output_path.parent != Path("") else Path(".")
    failed_all_path = parent / f"{stem}, failed all case ids.txt"
    failed_api_ok_path = parent / f"{stem}, failed api ok case ids.txt"
    failed_api_error_path = parent / f"{stem}, failed api error case ids.txt"
    write_case_id_list(failed_all_path, failed_all_case_ids)
    write_case_id_list(failed_api_ok_path, failed_api_ok_case_ids)
    write_case_id_list(failed_api_error_path, failed_api_error_case_ids)

    diff: dict[str, list[str]] | None = None
    if args.compare_with:
        prev_path = resolve_existing_path(args.compare_with)
        prev_data = json.loads(prev_path.read_text(encoding="utf-8"))
        prev_results = list(prev_data.get("results", []))
        diff = build_diff(prev_results, results)

    report = {
        "summary": summary,
        "lists": {
            "failed_all_case_ids_file": str(failed_all_path),
            "failed_api_ok_case_ids_file": str(failed_api_ok_path),
            "failed_api_error_case_ids_file": str(failed_api_error_path),
            "failed_all_case_ids_count": len(failed_all_case_ids),
            "failed_api_ok_case_ids_count": len(failed_api_ok_case_ids),
            "failed_api_error_case_ids_count": len(failed_api_error_case_ids),
        },
        "diff": diff,
        "results": results,
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 80)
    print(
        f"{Ansi.CYAN}PASS/FAIL SUMMARY (all): {Ansi.RESET}"
        f"passed={summary['passed']} failed={summary['failed']} "
        f"pass_rate={summary['pass_rate']}%"
    )
    print(
        f"{Ansi.CYAN}PASS/FAIL SUMMARY (api_ok_only): {Ansi.RESET}"
        f"passed={summary['api_ok_passed']} failed={summary['api_ok_failed']} "
        f"pass_rate={summary['api_ok_pass_rate']}% "
        f"(api_ok={summary['api_ok_count']}, api_error={summary['api_error_count']})"
    )
    print(
        f"Rate limit hits={summary['rate_limit_hits']}, retries={summary['rate_limit_retries_total']}"
    )
    print(f"Failed all IDs file: {failed_all_path.resolve()}")
    print(f"Failed api-ok IDs file: {failed_api_ok_path.resolve()}")
    print(f"Failed api-error IDs file: {failed_api_error_path.resolve()}")
    if diff is not None:
        print(
            f"Diff vs {args.compare_with}: "
            f"improved={len(diff['improved'])} "
            f"regressed={len(diff['regressed'])} "
            f"still_failed={len(diff['still_failed'])}"
        )
    print(f"Detailed results saved to: {output_path.resolve()}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
