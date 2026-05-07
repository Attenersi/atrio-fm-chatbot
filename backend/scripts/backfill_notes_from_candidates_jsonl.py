#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _norm_input(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _load_rows(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        key = _norm_input(str(obj.get("input", "")))
        if not key:
            continue
        rows.append(
            (
                key,
                str(obj.get("human_notes", "") or ""),
                str(obj.get("reasoning", "") or ""),
            )
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill training_examples.human_notes/reasoning from legacy candidates JSONL. "
            "Matches rows by normalized input text."
        )
    )
    parser.add_argument(
        "--jsonl",
        default="data/fine_tuning_v1_candidates.jsonl",
        help="Path to source candidates jsonl",
    )
    parser.add_argument(
        "--db",
        default="tickets.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print stats and sample diffs; do not write changes",
    )
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl).resolve()
    db_path = Path(args.db).resolve()
    if not jsonl_path.exists():
        raise SystemExit(f"JSONL file not found: {jsonl_path}")
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    rows = _load_rows(jsonl_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    matched = 0
    to_update = 0
    samples: list[tuple[int, str, str, str, str]] = []
    for norm_inp, notes, reasoning in rows:
        db_rows = cur.execute(
            "SELECT id, human_notes, reasoning FROM training_examples WHERE normalized_input = ?",
            (norm_inp,),
        ).fetchall()
        if not db_rows:
            continue
        for r in db_rows:
            matched += 1
            old_notes = str(r["human_notes"] or "")
            old_reasoning = str(r["reasoning"] or "")
            if old_notes != notes or old_reasoning != reasoning:
                to_update += 1
                if len(samples) < 10:
                    samples.append((int(r["id"]), old_notes, notes, old_reasoning, reasoning))

    print(f"json_rows={len(rows)}")
    print(f"matched_db_rows={matched}")
    print(f"rows_to_update={to_update}")
    for item in samples:
        ex_id, old_n, new_n, old_r, new_r = item
        print("---")
        print(f"id={ex_id}")
        print(f"old_human_notes={old_n[:140]}")
        print(f"new_human_notes={new_n[:140]}")
        print(f"old_reasoning={old_r[:140]}")
        print(f"new_reasoning={new_r[:140]}")

    if args.dry_run:
        conn.close()
        return 0

    backup_path = db_path.with_name(
        f"{db_path.stem}.backup_before_notes_backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
    )
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    src.backup(dst)
    dst.close()
    src.close()

    updated = 0
    for norm_inp, notes, reasoning in rows:
        cur.execute(
            """
            UPDATE training_examples
            SET human_notes = ?, reasoning = ?
            WHERE normalized_input = ?
              AND (COALESCE(human_notes, '') <> ? OR COALESCE(reasoning, '') <> ?)
            """,
            (notes, reasoning, norm_inp, notes, reasoning),
        )
        updated += cur.rowcount
    conn.commit()
    conn.close()
    print(f"backup_created={backup_path}")
    print(f"rows_updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
