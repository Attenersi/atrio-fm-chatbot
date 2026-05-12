"""Attach supporting training-example previews to analyzer API responses."""

from __future__ import annotations

from typing import Any

from .config import SUPPORTING_EXAMPLES_CAP as _SUPPORTING_EXAMPLES_CAP
from .database import get_training_examples_review_items_by_ids
from .prompt_analyzer import compact_training_example_for_analysis_api

SUPPORTING_EXAMPLES_CAP = _SUPPORTING_EXAMPLES_CAP


def build_example_lookup_from_signals(signals: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """First-seen example dict per id from suppressed review ``signals`` groups."""
    out: dict[int, dict[str, Any]] = {}
    for g in signals.get("groups") or []:
        if not isinstance(g, dict):
            continue
        for ex in g.get("examples") or []:
            if not isinstance(ex, dict) or ex.get("id") is None:
                continue
            try:
                eid = int(ex["id"])
            except (TypeError, ValueError):
                continue
            out.setdefault(eid, ex)
    return out


def collect_affected_ids_from_analysis_payload(payload: dict[str, Any]) -> list[int]:
    """Unique ids in payload order: all groups, then all rag_suggestions."""
    seen: set[int] = set()
    ordered: list[int] = []
    for g in payload.get("groups") or []:
        if not isinstance(g, dict):
            continue
        for x in g.get("affected_ids") or []:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if i not in seen:
                seen.add(i)
                ordered.append(i)
    for r in payload.get("rag_suggestions") or []:
        if not isinstance(r, dict):
            continue
        for x in r.get("affected_ids") or []:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if i not in seen:
                seen.add(i)
                ordered.append(i)
    return ordered


def _attach_supporting_to_block(
    block: dict[str, Any],
    lookup: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    out = dict(block)
    ids: list[int] = []
    for x in out.get("affected_ids") or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    slim_list: list[dict[str, Any]] = []
    truncated_after = 0
    for idx, eid in enumerate(ids):
        if idx >= SUPPORTING_EXAMPLES_CAP:
            truncated_after = len(ids) - SUPPORTING_EXAMPLES_CAP
            break
        raw = lookup.get(eid)
        if raw is None:
            slim_list.append({"id": eid, "missing": True})
        else:
            slim_list.append(compact_training_example_for_analysis_api(raw))
    out["supporting_examples"] = slim_list
    if truncated_after > 0:
        out["supporting_examples_omitted_count"] = truncated_after
    return out


def enrich_analysis_payload_with_supporting_examples(
    payload: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    lookup = build_example_lookup_from_signals(signals)
    need = collect_affected_ids_from_analysis_payload(payload)
    missing = [i for i in need if i not in lookup]
    if missing:
        lookup.update(get_training_examples_review_items_by_ids(missing))

    groups_out: list[Any] = []
    for g in payload.get("groups") or []:
        if isinstance(g, dict):
            groups_out.append(_attach_supporting_to_block(g, lookup))
        else:
            groups_out.append(g)

    rag_out: list[Any] = []
    for r in payload.get("rag_suggestions") or []:
        if isinstance(r, dict):
            rag_out.append(_attach_supporting_to_block(r, lookup))
        else:
            rag_out.append(r)

    return {**payload, "groups": groups_out, "rag_suggestions": rag_out}


def _normalize_int_ids(raw: Any, *, key: str | None = None) -> list[int]:
    """Parse list of ints from a dict key or from a list."""
    if key is not None and isinstance(raw, dict):
        seq = raw.get(key) or []
    else:
        seq = raw or []
    if not isinstance(seq, list):
        return []
    out: list[int] = []
    for x in seq:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def enrich_prompt_override_rows(rows: list[Any]) -> list[Any]:
    """Add ``supporting_examples`` / ``supporting_examples_omitted_count`` to override rows.

    Uses the same compact shape as analyzer groups. Batch-fetches missing rows once.
    """
    if not rows:
        return rows
    seen: set[int] = set()
    ordered: list[int] = []
    for o in rows:
        if not isinstance(o, dict):
            continue
        for i in _normalize_int_ids(o, key="affected_example_ids"):
            if i not in seen:
                seen.add(i)
                ordered.append(i)
    lookup: dict[int, dict[str, Any]] = {}
    if ordered:
        lookup = get_training_examples_review_items_by_ids(ordered)
    out: list[Any] = []
    for o in rows:
        if not isinstance(o, dict):
            out.append(o)
            continue
        ids = _normalize_int_ids(o, key="affected_example_ids")
        block = {**o, "affected_ids": ids}
        enriched = _attach_supporting_to_block(block, lookup)
        enriched.pop("affected_ids", None)
        out.append(enriched)
    return out
