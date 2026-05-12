from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .config import (
    EMBEDDING_DEDUP_COSINE_THRESHOLD,
    EMBEDDING_DEDUP_ENABLED,
    EMBEDDING_DEDUP_LOWER_BOUND,
    EMBEDDING_DEDUP_UPPER_BOUND,
    SEQUENCE_DUPLICATE_THRESHOLD as _SEQUENCE_DUPLICATE_THRESHOLD,
    TOKEN_DUPLICATE_THRESHOLD as _TOKEN_DUPLICATE_THRESHOLD,
)


SEQUENCE_DUPLICATE_THRESHOLD = _SEQUENCE_DUPLICATE_THRESHOLD
TOKEN_DUPLICATE_THRESHOLD = _TOKEN_DUPLICATE_THRESHOLD

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "when",
    "with",
}


def normalize_rule_text(text: str) -> str:
    """Normalize rule-like text for exact and near-duplicate comparisons."""
    cleaned = (text or "").lower()
    cleaned = re.sub(r"^[\s>*#\-\d.)]+", " ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]{3,}", normalize_rule_text(text))
        if t not in _STOP_WORDS
    }


def _token_jaccard(a: str, b: str) -> float:
    ta = _tokens(a)
    tb = _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _sequence_ratio(a: str, b: str) -> float:
    na = normalize_rule_text(a)
    nb = normalize_rule_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def rule_similarity(a: str, b: str) -> float:
    """Heuristic similarity in ``[0, 1]`` for clustering related rule fragments.

    Uses the larger of sequence ratio and token Jaccard (same signals as duplicate
    detection, but returned as a single score for greedy clustering).
    """
    if not (a or "").strip() or not (b or "").strip():
        return 0.0
    return max(_sequence_ratio(a, b), _token_jaccard(a, b))


def _prompt_candidate_chunks(system_prompt: str) -> list[str]:
    """Extract bullets and short paragraphs that can be compared to a rule.

    The system prompt mixes headings, prose, and rule bullets. We keep bullets
    and compact paragraphs, ignoring template placeholders and very long blocks
    like DOCUMENTATION / JSON schema.
    """
    chunks: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        text = " ".join(line.strip() for line in paragraph if line.strip()).strip()
        paragraph = []
        if 35 <= len(text) <= 420 and "{" not in text and "}" not in text:
            chunks.append(text)

    for raw in (system_prompt or "").splitlines():
        line = raw.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("##") or line.endswith(":"):
            flush_paragraph()
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            flush_paragraph()
            text = bullet.group(1).strip()
            if 12 <= len(text) <= 420:
                chunks.append(text)
            continue
        if "{context}" in line or "{query}" in line:
            flush_paragraph()
            continue
        paragraph.append(line)
    flush_paragraph()

    seen: set[str] = set()
    unique: list[str] = []
    for chunk in chunks:
        key = normalize_rule_text(chunk)
        if key and key not in seen:
            seen.add(key)
            unique.append(chunk)
    return unique


def build_existing_rule_candidates(
    system_prompt: str, active_overrides: list[dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    candidates = [
        {"source": "system_prompt", "text": chunk}
        for chunk in _prompt_candidate_chunks(system_prompt)
    ]
    for override in active_overrides or []:
        approved = str(override.get("approved_change") or "").strip()
        if approved:
            oid = override.get("id")
            source = f"active_override:{oid}" if oid is not None else "active_override"
            candidates.append({"source": source, "text": approved})
    return candidates


def find_duplicate_rule(
    rule_text: str,
    system_prompt: str,
    active_overrides: list[dict[str, Any]] | None = None,
    *,
    use_embedding_fallback: bool | None = None,
) -> dict[str, Any]:
    """Return duplicate metadata for a proposed rule.

    Two-stage filter:

    1. Cheap pass: token Jaccard + ``SequenceMatcher``. Catches blatant
       duplicates with zero LLM cost.
    2. Borderline pass (only when ``EMBEDDING_DEDUP_ENABLED``): if the
       cheap-pass score lands in the ambiguous band
       ``[EMBEDDING_DEDUP_LOWER_BOUND, EMBEDDING_DEDUP_UPPER_BOUND]``,
       run :func:`prompt_rule_embeddings.cosine_search` and treat
       cosine ≥ ``EMBEDDING_DEDUP_COSINE_THRESHOLD`` as a confirmed
       duplicate. The cheap pass is the source of truth for outright
       hits and outright misses.

    Pass ``use_embedding_fallback=False`` to force the cheap-only path
    (used by tests and the discarded-suggestion filter that runs against
    a much larger candidate set).
    """
    normalized = normalize_rule_text(rule_text)
    if not normalized:
        return {
            "is_duplicate": False,
            "score": 0.0,
            "source": "",
            "matched_text": "",
            "match_type": "",
        }

    candidates = build_existing_rule_candidates(system_prompt, active_overrides)

    best = {
        "is_duplicate": False,
        "score": 0.0,
        "source": "",
        "matched_text": "",
        "match_type": "",
    }
    for candidate in candidates:
        text = candidate["text"]
        candidate_norm = normalize_rule_text(text)
        if not candidate_norm:
            continue
        exact = normalized == candidate_norm
        seq = _sequence_ratio(rule_text, text)
        jac = _token_jaccard(rule_text, text)
        if exact:
            score = 1.0
            match_type = "exact"
        elif seq >= SEQUENCE_DUPLICATE_THRESHOLD:
            score = seq
            match_type = "sequence"
        elif jac >= TOKEN_DUPLICATE_THRESHOLD:
            score = jac
            match_type = "token_overlap"
        else:
            score = max(seq, jac)
            match_type = "near"

        if score > float(best["score"]):
            best = {
                "is_duplicate": bool(
                    exact
                    or seq >= SEQUENCE_DUPLICATE_THRESHOLD
                    or jac >= TOKEN_DUPLICATE_THRESHOLD
                ),
                "score": round(float(score), 4),
                "source": candidate["source"],
                "matched_text": text,
                "match_type": match_type,
            }

    fallback_enabled = (
        EMBEDDING_DEDUP_ENABLED if use_embedding_fallback is None else bool(use_embedding_fallback)
    )
    if (
        fallback_enabled
        and not best["is_duplicate"]
        and EMBEDDING_DEDUP_LOWER_BOUND
        <= float(best["score"])
        < EMBEDDING_DEDUP_UPPER_BOUND
    ):
        embed_result = _embedding_second_stage(rule_text, candidates)
        if embed_result is not None:
            cosine_score, candidate = embed_result
            if cosine_score >= EMBEDDING_DEDUP_COSINE_THRESHOLD and candidate:
                best = {
                    "is_duplicate": True,
                    "score": round(float(cosine_score), 4),
                    "source": candidate["source"],
                    "matched_text": candidate["text"],
                    "match_type": "embedding",
                }

    return best


def _embedding_second_stage(
    rule_text: str, candidates: list[dict[str, str]]
) -> tuple[float, dict[str, str] | None] | None:
    """Lazily import embedding helper so test environments without the
    embedding service / network dependency don't pay the import cost
    until they actually exercise the borderline path.
    """
    try:
        from .prompt_rule_embeddings import cosine_search
    except Exception:
        return None
    try:
        return cosine_search(rule_text, candidates)
    except Exception:
        return None


def filter_duplicate_suggestions(
    groups: list[dict[str, Any]],
    system_prompt: str,
    active_overrides: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visible: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    for group in groups:
        suggestion = str(group.get("suggested_change") or "")
        match = find_duplicate_rule(suggestion, system_prompt, active_overrides)
        if match.get("is_duplicate"):
            hidden.append(
                {
                    "type": group.get("type", ""),
                    "suggested_change": suggestion,
                    **match,
                }
            )
        else:
            visible.append(group)
    return visible, hidden


def filter_discarded_suggestions(
    groups: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Hide groups whose ``suggested_change`` is too close to a stored discard.

    Uses the same thresholds as :func:`filter_duplicate_suggestions`. When both
    the group and the decision row have a non-empty ``type`` / ``error_type``,
    they must match before treating the discard as relevant.
    """
    visible: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    for group in groups:
        suggestion = str(group.get("suggested_change") or "")
        g_type = str(group.get("type") or "").strip()
        hit: tuple[dict[str, Any], str, float] | None = None
        for d in decisions or []:
            dt = str(d.get("suggested_change") or "").strip()
            if not dt:
                continue
            d_type = str(d.get("error_type") or "").strip()
            if g_type and d_type and g_type != d_type:
                continue
            if normalize_rule_text(suggestion) == normalize_rule_text(dt):
                hit = (d, "exact", 1.0)
                break
            seq = _sequence_ratio(suggestion, dt)
            if seq >= SEQUENCE_DUPLICATE_THRESHOLD:
                hit = (d, "sequence", seq)
                break
            jac = _token_jaccard(suggestion, dt)
            if jac >= TOKEN_DUPLICATE_THRESHOLD:
                hit = (d, "token_overlap", jac)
                break
        if hit:
            dec, mtype, _score = hit
            hidden.append(
                {
                    "type": group.get("type", ""),
                    "suggested_change": suggestion,
                    "match_type": mtype,
                    "decision_id": dec.get("id"),
                    "discarded_suggestion": str(dec.get("suggested_change") or ""),
                }
            )
        else:
            visible.append(group)
    return visible, hidden
