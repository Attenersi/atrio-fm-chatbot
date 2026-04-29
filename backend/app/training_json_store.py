from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any

from .config import TRAINING_DATA_DIR

_LOCK = threading.Lock()
_CANDIDATES_FILE = "fine_tuning_v1_candidates.jsonl"
_STATUS_ALLOWED = {"pending", "approved", "edited", "rejected"}
_STATUS_ALIASES = {"corrected": "edited"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def _normalize_status(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = _STATUS_ALIASES.get(raw, raw)
    return raw if raw in _STATUS_ALLOWED else "pending"


def _default_candidates_path() -> Path:
    root = Path(TRAINING_DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root / _CANDIDATES_FILE


def _record_key(item: dict[str, Any]) -> str:
    item_id_raw = item.get("id")
    try:
        item_id_int = int(item_id_raw)
    except Exception:
        item_id_int = 0
    if item_id_int > 0:
        # Prefer stable DB id when available so each logged example can be kept
        # as a separate record (append-like behavior across repeated test runs).
        item_id = str(item_id_int)
        return f"id:{item_id}"
    source_type = str(item.get("source_type", "")).strip()
    source_id = str(item.get("source_id", "")).strip()
    source_ref = str(item.get("source_ref", "")).strip()
    if source_type and source_id:
        return f"{source_type}:{source_id}:{source_ref}"
    payload = f"{item.get('input', '')}|{source_type}|{source_id}|{source_ref}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"hash:{digest}"


def _status_rank(status: str) -> int:
    ranks = {"edited": 4, "approved": 3, "pending": 2, "rejected": 1}
    return ranks.get(_normalize_status(status), 0)


def _choose_preferred(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    c_rank = _status_rank(str(current.get("correction_type", "")))
    n_rank = _status_rank(str(candidate.get("correction_type", "")))
    if n_rank != c_rank:
        return candidate if n_rank > c_rank else current
    c_ts = str(current.get("reviewed_at") or current.get("created_at") or "")
    n_ts = str(candidate.get("reviewed_at") or candidate.get("created_at") or "")
    return candidate if n_ts >= c_ts else current


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _canonical_record(row)
        key = _record_key(item)
        if key not in dedup:
            dedup[key] = item
            continue
        dedup[key] = _choose_preferred(dedup[key], item)
    return list(dedup.values())


def _canonical_record(item: dict[str, Any]) -> dict[str, Any]:
    input_text = str(item.get("input") or item.get("input_text") or "").strip()
    ideal = item.get("ideal_output")
    if not isinstance(ideal, dict):
        ideal = {}
    actual = item.get("actual_output")
    if not isinstance(actual, dict):
        actual = {}
    ctx = item.get("context_used")
    if not isinstance(ctx, list):
        ctx = []
    ctx = [str(x) for x in ctx]
    correction_type = _normalize_status(str(item.get("correction_type", "pending")))
    reviewed_at = item.get("reviewed_at")
    if correction_type != "pending" and not reviewed_at:
        reviewed_at = _utc_now_iso()
    if correction_type == "pending":
        reviewed_at = None

    return {
        "id": int(item.get("id", 0) or 0),
        "input": input_text,
        "actual_output": actual,
        "ideal_output": ideal,
        "human_notes": str(item.get("human_notes", "") or ""),
        "correction_type": correction_type,
        "context_used": ctx,
        "reasoning": str(item.get("reasoning", "") or ""),
        "source_type": str(item.get("source_type", "") or ""),
        "source_id": str(item.get("source_id", "") or ""),
        "source_ref": str(item.get("source_ref", "") or ""),
        "user_role": str(item.get("user_role", "") or ""),
        "query_type": str(item.get("query_type", "") or ""),
        "ticket_id": item.get("ticket_id"),
        "created_at": str(item.get("created_at", "") or _utc_now_iso()),
        "reviewed_at": reviewed_at,
        "knowledge_gap_logged": bool(item.get("knowledge_gap_logged", False)),
        "knowledge_gap_reason": str(item.get("knowledge_gap_reason", "") or ""),
    }


def _to_api_shape(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item.get("id", 0) or 0),
        "input_text": item.get("input", ""),
        "actual_output": item.get("actual_output", {}),
        "ideal_output": item.get("ideal_output", {}),
        "human_notes": item.get("human_notes", ""),
        "correction_type": _normalize_status(str(item.get("correction_type", "pending"))),
        "context_used": item.get("context_used", []),
        "reasoning": item.get("reasoning", ""),
        "used_sources": item.get("context_used", []),
        "context_count": len(item.get("context_used", [])),
        "query_type": item.get("query_type", ""),
        "in_scope": "",
        "grounded": "",
        "ticket_created": bool((item.get("ideal_output") or {}).get("create_ticket")),
        "ticket_id": item.get("ticket_id"),
        "user_id": None,
        "user_role": item.get("user_role", ""),
        "model": "",
        "run_id": "",
        "source_type": item.get("source_type", ""),
        "source_id": item.get("source_id", ""),
        "source_ref": item.get("source_ref", ""),
        "knowledge_gap_logged": bool(item.get("knowledge_gap_logged", False)),
        "knowledge_gap_reason": item.get("knowledge_gap_reason", ""),
        "created_at": item.get("created_at", ""),
        "reviewed_at": item.get("reviewed_at"),
    }


def load_candidates(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path else _default_candidates_path()
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        data = _json_load(stripped, None)
        if isinstance(data, dict):
            rows.append(_canonical_record(data))
    return rows


def save_candidates(rows: list[dict[str, Any]], path: str | Path | None = None) -> None:
    target = Path(path) if path else _default_candidates_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    compact_rows = _dedupe_rows(rows)
    body = "\n".join(_json_dump(_canonical_record(r)) for r in compact_rows)
    if body:
        body += "\n"
    target.write_text(body, encoding="utf-8")


def upsert_candidate(record: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    with _LOCK:
        rows = load_candidates(path)
        next_item = _canonical_record(record)
        idx = -1
        next_key = _record_key(next_item)
        for i, row in enumerate(rows):
            if _record_key(row) == next_key:
                idx = i
                break
        if idx >= 0:
            current = rows[idx]
            # Keep latest manual state if incoming seed is weaker.
            if _normalize_status(str(current.get("correction_type"))) in {"edited", "approved"} and _normalize_status(
                str(next_item.get("correction_type"))
            ) == "pending":
                next_item["correction_type"] = current["correction_type"]
                next_item["ideal_output"] = current.get("ideal_output", next_item.get("ideal_output", {}))
                next_item["human_notes"] = current.get("human_notes", "")
                next_item["reasoning"] = current.get("reasoning", "")
                next_item["context_used"] = current.get("context_used", [])
                next_item["reviewed_at"] = current.get("reviewed_at")
            rows[idx] = next_item
        else:
            rows.append(next_item)
        save_candidates(rows, path)
        return next_item


def bootstrap_from_examples(examples: list[dict[str, Any]], path: str | Path | None = None) -> int:
    with _LOCK:
        existing = load_candidates(path)
        if existing:
            return len(existing)
        rows: list[dict[str, Any]] = []
        for row in examples:
            rows.append(
                _canonical_record(
                    {
                        "id": row.get("id"),
                        "input": row.get("input_text", ""),
                        "actual_output": row.get("actual_output", {}),
                        "ideal_output": row.get("ideal_output") or row.get("actual_output", {}),
                        "human_notes": row.get("human_notes", ""),
                        "correction_type": row.get("correction_type", "pending"),
                        "context_used": row.get("context_used", []),
                        "reasoning": row.get("reasoning", ""),
                        "source_type": row.get("source_type", ""),
                        "source_id": row.get("source_id", ""),
                        "source_ref": row.get("source_ref", ""),
                        "user_role": row.get("user_role", ""),
                        "query_type": row.get("query_type", ""),
                        "ticket_id": row.get("ticket_id"),
                        "created_at": row.get("created_at"),
                        "reviewed_at": row.get("reviewed_at"),
                        "knowledge_gap_logged": row.get("knowledge_gap_logged", False),
                        "knowledge_gap_reason": row.get("knowledge_gap_reason", ""),
                    }
                )
            )
        save_candidates(rows, path)
        return len(_dedupe_rows(rows))


def list_candidates_for_api(
    *,
    correction_type: str | None = None,
    user_role: str | None = None,
    limit: int = 200,
    offset: int = 0,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    rows = load_candidates(path)
    rows = sorted(rows, key=lambda r: str(r.get("created_at", "")), reverse=True)
    if correction_type:
        want = _normalize_status(correction_type)
        rows = [r for r in rows if _normalize_status(str(r.get("correction_type", ""))) == want]
    if user_role:
        rows = [r for r in rows if str(r.get("user_role", "")) == user_role]
    start = max(0, offset)
    stop = start + max(1, limit)
    return [_to_api_shape(r) for r in rows[start:stop]]


def get_candidate_for_api(example_id: int, path: str | Path | None = None) -> dict[str, Any]:
    rows = load_candidates(path)
    for row in rows:
        if int(row.get("id", 0) or 0) == int(example_id):
            return _to_api_shape(row)
    return {}


def update_candidate_review_for_api(
    *,
    example_id: int,
    correction_type: str,
    ideal_output: dict[str, Any] | None = None,
    human_notes: str | None = None,
    context_used: list[str] | None = None,
    reasoning: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    with _LOCK:
        rows = load_candidates(path)
        for idx, row in enumerate(rows):
            if int(row.get("id", 0) or 0) != int(example_id):
                continue
            next_row = dict(row)
            next_row["correction_type"] = _normalize_status(correction_type)
            if ideal_output is not None:
                next_row["ideal_output"] = ideal_output
            if human_notes is not None:
                next_row["human_notes"] = human_notes
            if context_used is not None:
                next_row["context_used"] = list(context_used)
            if reasoning is not None:
                next_row["reasoning"] = reasoning
            next_row["reviewed_at"] = _utc_now_iso() if next_row["correction_type"] != "pending" else None
            rows[idx] = _canonical_record(next_row)
            save_candidates(rows, path)
            return _to_api_shape(rows[idx])
    return {}


def build_dataset_view(path: str | Path | None = None) -> dict[str, Any]:
    rows = [_to_api_shape(r) for r in load_candidates(path)]
    train_rows = [r for r in rows if _normalize_status(str(r.get("correction_type", ""))) == "edited"]
    review_rows = [r for r in rows if _normalize_status(str(r.get("correction_type", ""))) in {"pending", "rejected"}]
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        s = _normalize_status(str(row.get("correction_type", "")))
        by_status[s] = by_status.get(s, 0) + 1
        src = str(row.get("source_type", "") or "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    return {
        "all_rows": rows,
        "train_rows": train_rows,
        "review_rows": review_rows,
        "manifest": {
            "version": "json-first-v1",
            "total_raw_rows": len(rows),
            "train_rows": len(train_rows),
            "review_rows": len(review_rows),
            "by_status": by_status,
            "by_source_type": by_source,
            "updated_at": _utc_now_iso(),
        },
    }


def export_jsonl(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        ideal = row.get("ideal_output") or row.get("actual_output") or {}
        lines.append(
            _json_dump(
                {
                    "id": row.get("id"),
                    "input": row.get("input_text", ""),
                    "ideal_output": {
                        "category": ideal.get("category"),
                        "priority": ideal.get("priority"),
                        "create_ticket": bool(ideal.get("create_ticket")),
                        "response": ideal.get("response"),
                        "issue_summary": ideal.get("issue_summary"),
                    },
                    "human_notes": row.get("human_notes", ""),
                    "correction_type": _normalize_status(str(row.get("correction_type", "pending"))),
                    "context_used": row.get("context_used", []),
                    "reasoning": row.get("reasoning", ""),
                    "source_type": row.get("source_type", ""),
                    "source_id": row.get("source_id", ""),
                    "source_ref": row.get("source_ref", ""),
                    "created_at": row.get("created_at", ""),
                }
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def mass_mark_all_edited_if_any_custom_reasoning(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else _default_candidates_path()
    rows = load_candidates(target)
    marker = "seeded from test suite result"
    has_custom_reasoning = any(str(r.get("reasoning", "") or "").strip().lower() != marker for r in rows)
    if not has_custom_reasoning:
        return {"changed": 0, "total": len(rows), "applied": False, "backup_path": None}
    backup_path = None
    if target.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = target.with_name(f"{target.stem}.backup_mass_edit_{ts}{target.suffix}")
        shutil.copyfile(target, backup)
        backup_path = str(backup)
    changed = 0
    updated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if _normalize_status(str(item.get("correction_type", ""))) != "edited":
            item["correction_type"] = "edited"
            item["reviewed_at"] = _utc_now_iso()
            changed += 1
        updated.append(_canonical_record(item))
    save_candidates(updated, target)
    return {"changed": changed, "total": len(rows), "applied": True, "backup_path": backup_path}
