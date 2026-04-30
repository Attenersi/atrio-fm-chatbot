"""One-shot parser that extracts structured mismatch info from existing
`human_notes` strings into the new Faza A columns:
  - mismatch_fields  (JSON list[str])
  - expected_payload (JSON dict)
  - actual_payload   (JSON dict)

Idempotent: reads only rows where any of these columns is still default
('[]' / '{}'), so re-running won't overwrite manual edits.

Usage:
    cd backend
    ../venv/bin/python -m scripts.backfill_mismatch_fields           # write
    ../venv/bin/python -m scripts.backfill_mismatch_fields --dry-run # report only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Allow running as `python -m scripts.backfill_mismatch_fields` from backend/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import get_conn, init_db, update_training_example_mismatch  # noqa: E402


# Patterns from the seed test runner output (test_rag.py):
#   "Needs review: category expected=Plumbing actual=HVAC"
#   "Needs review: priority expected=HIGH actual=URGENT"
#   "Needs review: ticket_created expected=True actual=False"
#   "Needs review: response missing tokens=['hours','contact']"
# Multi-issue records use " | " as separator (e.g. record 425):
#   "Needs review: ticket_created expected=True actual=False | category expected=Safety actual=General"
_RX_FIELD = re.compile(
    r"\b(?P<field>category|priority|ticket_created)\s+expected=(?P<exp>[^\s|]+)\s+actual=(?P<act>[^\s|]+)",
    re.IGNORECASE,
)
_RX_TOKENS = re.compile(r"response\s+missing\s+tokens=(?P<list>\[[^\]]*\])", re.IGNORECASE)
_AUTO_APPROVED = "auto-approved from passing test case"


def parse_human_notes(notes: str) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Return (mismatch_fields, expected_payload, actual_payload).
    Empty result for notes that don't follow the test runner pattern."""
    if not notes:
        return [], {}, {}
    if _AUTO_APPROVED in notes.lower():
        return [], {}, {}

    fields: list[str] = []
    expected: dict[str, Any] = {}
    actual: dict[str, Any] = {}

    for match in _RX_FIELD.finditer(notes):
        field = match.group("field").lower()
        exp_raw = match.group("exp").strip().rstrip(",")
        act_raw = match.group("act").strip().rstrip(",")
        if field == "ticket_created":
            if exp_raw.lower() in {"true", "false"}:
                expected[field] = exp_raw.lower() == "true"
            if act_raw.lower() in {"true", "false"}:
                actual[field] = act_raw.lower() == "true"
            fields.append("ticket_missing" if expected.get(field) and not actual.get(field) else "ticket_created")
        else:
            expected[field] = exp_raw
            actual[field] = act_raw
            fields.append(f"{field}_mismatch")

    tokens_match = _RX_TOKENS.search(notes)
    if tokens_match:
        raw_list = tokens_match.group("list")
        # Tolerate both Python repr-ish ['a','b'] and JSON ["a","b"].
        try:
            parsed = json.loads(raw_list.replace("'", '"'))
            if isinstance(parsed, list):
                expected["response_tokens"] = [str(x) for x in parsed]
        except Exception:
            pass
        fields.append("response_tokens_missing")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped, expected, actual


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = ap.parse_args()

    init_db()

    counts: dict[str, int] = {}
    total = 0
    parsed = 0
    skipped_already_filled = 0
    candidates: list[tuple[int, str, list[str], dict, dict]] = []

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, human_notes, mismatch_fields FROM training_examples"
        ).fetchall()

    for row in rows:
        total += 1
        existing_fields = row["mismatch_fields"] or "[]"
        try:
            existing = json.loads(existing_fields)
        except Exception:
            existing = []
        # If a row already has mismatch_fields, leave it alone (idempotent).
        if existing:
            skipped_already_filled += 1
            continue

        fields, expected, actual = parse_human_notes(row["human_notes"] or "")
        if not fields:
            continue
        parsed += 1
        for f in fields:
            counts[f] = counts.get(f, 0) + 1
        candidates.append((int(row["id"]), row["human_notes"] or "", fields, expected, actual))

    print(f"Scanned {total} rows; {skipped_already_filled} already filled; {parsed} parseable.")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<28}  {v}")

    if args.dry_run:
        print("\nDry run; no DB writes.")
        # Show 3 sample mappings.
        for ex in candidates[:3]:
            print(f"  id={ex[0]} fields={ex[2]} expected={ex[3]} actual={ex[4]}  notes={ex[1][:80]!r}")
        return 0

    written = 0
    for ex_id, _notes, fields, expected, actual in candidates:
        update_training_example_mismatch(
            ex_id,
            mismatch_fields=fields,
            expected_payload=expected,
            actual_payload=actual,
        )
        written += 1
    print(f"\nWrote {written} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
