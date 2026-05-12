"""Filter analyzer output by training-example IDs already claimed for prompt rules."""

from __future__ import annotations

from typing import Any


def _int_ids(raw: Any) -> list[int]:
    out: list[int] = []
    for x in raw or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def filter_payload_by_claimed_examples(
    payload: dict[str, Any],
    claimed: set[int],
) -> dict[str, Any]:
    """Drop groups / RAG items whose every ``affected_id`` is in ``claimed``."""
    if not claimed:
        return payload
    hidden: list[dict[str, Any]] = []
    vis_groups: list[dict[str, Any]] = []
    for group in payload.get("groups") or []:
        if not isinstance(group, dict):
            continue
        aff = _int_ids(group.get("affected_ids"))
        if aff and all(a in claimed for a in aff):
            hidden.append(
                {
                    "kind": "group",
                    "type": group.get("type", ""),
                    "suggested_change": group.get("suggested_change", ""),
                    "affected_ids": aff,
                    "reason": "question_bank_claimed",
                }
            )
        else:
            vis_groups.append(group)

    vis_rag: list[dict[str, Any]] = []
    for r in payload.get("rag_suggestions") or []:
        if not isinstance(r, dict):
            continue
        aff = _int_ids(r.get("affected_ids"))
        if aff and all(a in claimed for a in aff):
            hidden.append(
                {
                    "kind": "rag",
                    "type": r.get("type", ""),
                    "description": (r.get("description") or "")[:200],
                    "affected_ids": aff,
                    "reason": "question_bank_claimed",
                }
            )
        else:
            vis_rag.append(r)

    out = {
        **payload,
        "groups": vis_groups,
        "rag_suggestions": vis_rag,
    }
    if hidden:
        out["question_claim_hidden"] = len(hidden)
        out["question_claim_matches"] = hidden
    else:
        out.setdefault("question_claim_hidden", 0)
        out.setdefault("question_claim_matches", [])
    return out
