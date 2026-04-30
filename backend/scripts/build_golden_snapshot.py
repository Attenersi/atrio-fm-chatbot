"""Build a golden eval-set from training_examples.

Picks ~60 `correction_type='approved'` rows (cleanest signal) plus up to 20
`pending` rows that already have structured `expected_payload` (Faza A) so
the eval can score them. Writes `data/eval_golden.jsonl`.

Usage:
    cd backend
    ../venv/bin/python -m scripts.build_golden_snapshot --approved 60 --pending 20
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import get_conn, init_db  # noqa: E402


def _row_to_case(row: dict) -> dict | None:
    """Translate a training_examples row into eval_golden.jsonl shape.
    For `approved` rows the ideal_output IS the expected outcome.
    For `pending` rows the expected_payload (Faza A) provides the corrections."""
    ideal = row.get("ideal_output") or {}
    expected_payload = row.get("expected_payload") or {}
    msg = (row.get("input_text") or "").strip()
    if not msg:
        return None
    case: dict = {"id": f"te-{row['id']}", "message": msg}

    if row["correction_type"] == "approved":
        if ideal.get("category"):
            case["expected_category"] = ideal["category"]
        if ideal.get("priority"):
            case["expected_priority"] = ideal["priority"]
        if "create_ticket" in ideal:
            case["expected_ticket_created"] = bool(ideal["create_ticket"])
    else:  # pending: pull structured corrections from Faza A
        if expected_payload.get("category"):
            case["expected_category"] = expected_payload["category"]
        if expected_payload.get("priority"):
            case["expected_priority"] = expected_payload["priority"]
        if "ticket_created" in expected_payload:
            case["expected_ticket_created"] = bool(expected_payload["ticket_created"])
        if expected_payload.get("response_tokens"):
            case["expected_in_response"] = expected_payload["response_tokens"]

    # Skip cases with no checkable expectation.
    if not any(
        k in case
        for k in (
            "expected_category",
            "expected_priority",
            "expected_ticket_created",
            "expected_in_response",
        )
    ):
        return None
    return case


def _hydrate(row) -> dict:
    out = dict(row)
    out["ideal_output"] = json.loads(out.get("ideal_output_json") or "{}" or "{}")
    out["expected_payload"] = json.loads(out.get("expected_payload") or "{}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved", type=int, default=60)
    ap.add_argument("--pending", type=int, default=20)
    ap.add_argument("--out", default="data/eval_golden.jsonl")
    args = ap.parse_args()

    init_db()
    cases: list[dict] = []
    seen_msgs: set[str] = set()

    with get_conn() as conn:
        approved_rows = conn.execute(
            """
            SELECT id, input_text, correction_type, ideal_output_json, expected_payload
            FROM training_examples
            WHERE correction_type = 'approved' AND length(trim(input_text)) > 5
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(0, args.approved * 3),),  # over-fetch to allow dedup + skip
        ).fetchall()
        pending_rows = conn.execute(
            """
            SELECT id, input_text, correction_type, ideal_output_json, expected_payload
            FROM training_examples
            WHERE correction_type = 'pending'
              AND mismatch_fields != '[]'
              AND length(trim(input_text)) > 5
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(0, args.pending * 3),),
        ).fetchall()

    def _take(rows, target) -> int:
        added = 0
        for row in rows:
            if added >= target:
                break
            hyd = _hydrate(row)
            case = _row_to_case(hyd)
            if not case:
                continue
            msg_norm = case["message"].lower()
            if msg_norm in seen_msgs:
                continue
            seen_msgs.add(msg_norm)
            cases.append(case)
            added += 1
        return added

    n_approved = _take(approved_rows, args.approved)
    n_pending = _take(pending_rows, args.pending)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} golden cases ({n_approved} approved + {n_pending} pending) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
