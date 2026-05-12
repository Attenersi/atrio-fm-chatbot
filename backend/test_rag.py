"""CLI: run RAG/API chat tests against a live server (HTTP) and write JSON report."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag_eval import (  # noqa: E402
    TEST_RESULTS_DIR,
    ResponseTokenSpec,
    TestCase,
    build_builtin_cases,
    build_diff,
    build_test_cases_from_csv_bytes,
    build_test_cases_from_json_path,
    classify_failures,
    coerce_expected_in_response,
    coerce_str_list,
    evaluate_case,
    resolve_existing_path,
)


class Ansi:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        safe = text.encode("ascii", errors="replace").decode("ascii")
        print(safe)


def parse_case_ids_file(path: str) -> set[str]:
    rows = resolve_existing_path(path).read_text(encoding="utf-8").splitlines()
    return {row.strip() for row in rows if row.strip()}


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
    retries_used = 0
    while True:
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
    elif args.cases_csv.strip():
        desc = _slug_to_label(Path(args.cases_csv).stem)
    else:
        desc = "builtin cases"
    filename = f"{date_label}, {_safe_file_fragment(desc)}.json"
    return TEST_RESULTS_DIR / filename


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run RAG/API chat tests and output pass/fail report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  All cases passed and optional api_ok gates satisfied.
  1  One or more cases failed (logic or assertions).
  2  Unhandled runtime error (e.g. cannot reach API).
  3  api_ok quality gate failed (--min-api-ok-pass-rate / --min-api-ok-count).
""",
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
        help="Optional path to JSON test suite (e.g. tests/suites/ci_eval_smoke.json)",
    )
    parser.add_argument(
        "--cases-csv",
        default="",
        help="Optional path to CSV test suite (id, message, optional expectation columns)",
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
    parser.add_argument(
        "--min-api-ok-pass-rate",
        type=float,
        default=None,
        metavar="PCT",
        help=(
            "If set, require summary api_ok_pass_rate >= PCT (0-100). "
            "Requires at least one api_ok response. Exit code 3 if not met."
        ),
    )
    parser.add_argument(
        "--min-api-ok-count",
        type=int,
        default=0,
        metavar="N",
        help="If > 0, require at least N api_ok responses. Exit code 3 if not met.",
    )
    args = parser.parse_args()
    if args.min_api_ok_pass_rate is not None and not (0.0 <= args.min_api_ok_pass_rate <= 100.0):
        print("ERROR: --min-api-ok-pass-rate must be between 0 and 100.", file=sys.stderr)
        return 2

    sources = [bool(args.cases_file.strip()), bool(args.cases_csv.strip())]
    if sum(sources) > 1:
        print("ERROR: use at most one of --cases-file or --cases-csv.", file=sys.stderr)
        return 2

    client = ApiClient(args.base_url, timeout_seconds=args.timeout)

    print(f"Connecting to {args.base_url} and authenticating as '{args.username}'...")
    login_response = client.login(args.username, args.password)
    user_info = login_response.get("user", {})
    print(f"Authenticated: user={user_info.get('username')} role={user_info.get('role')}")

    if args.cases_file:
        cases = build_test_cases_from_json_path(args.cases_file)
    elif args.cases_csv:
        csv_path = resolve_existing_path(args.cases_csv)
        cases = build_test_cases_from_csv_bytes(csv_path.read_bytes())
    else:
        cases = build_builtin_cases()
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
    elif args.cases_csv:
        source_ref = resolve_existing_path(args.cases_csv).name
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

    exit_cases = 0 if failed == 0 else 1

    if args.min_api_ok_count > 0:
        if summary["api_ok_count"] < args.min_api_ok_count:
            _safe_print(
                f"{Ansi.RED}GATE: api_ok_count={summary['api_ok_count']} "
                f"< --min-api-ok-count={args.min_api_ok_count}{Ansi.RESET}"
            )
            return 3

    if args.min_api_ok_pass_rate is not None:
        if summary["api_ok_count"] < 1:
            _safe_print(
                f"{Ansi.RED}GATE: no api_ok responses; cannot verify "
                f"--min-api-ok-pass-rate={args.min_api_ok_pass_rate}{Ansi.RESET}"
            )
            return 3
        if summary["api_ok_pass_rate"] < args.min_api_ok_pass_rate:
            _safe_print(
                f"{Ansi.RED}GATE: api_ok_pass_rate={summary['api_ok_pass_rate']}% "
                f"< --min-api-ok-pass-rate={args.min_api_ok_pass_rate}{Ansi.RESET}"
            )
            return 3

    return exit_cases


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
