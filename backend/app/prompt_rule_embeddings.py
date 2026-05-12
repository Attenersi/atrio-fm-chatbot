"""Embedding-based second-stage dedup for analyzer suggestions.

The cheap heuristic in :mod:`prompt_rule_similarity` (token Jaccard +
``SequenceMatcher``) catches most blatant duplicates with zero LLM cost.
For *borderline* matches — where the cheap score sits in the ambiguous
band ``[EMBEDDING_DEDUP_LOWER_BOUND, EMBEDDING_DEDUP_UPPER_BOUND]`` —
we want a smarter signal that understands paraphrases. This module
provides that signal via the NVIDIA embedding model with a SQLite cache
keyed on the rule text's SHA-256 hash so we never embed the same string
twice.

Public surface:

- :func:`embed_rule(text)` — returns the embedding vector for one rule,
  hitting the cache transparently.
- :func:`cosine_search(query, candidates)` — returns ``(best_score,
  best_candidate)`` where ``candidates`` is a list of
  ``{"text": str, ...}`` dicts.
- :func:`cache_size()` — returns ``(rows, bytes)`` for the cache table
  (used by the admin audit endpoint).

The cache is created lazily on first write so test environments that
never invoke the dedup path don't pay the schema cost.
"""

from __future__ import annotations

import hashlib
import logging
import math
import sqlite3
import struct
from typing import Any, Iterable

from .config import EMBED_MODEL
from .database import get_conn
from .llm import embed

_log = logging.getLogger("fm.prompt_rule_embeddings")


def _rule_hash(text: str) -> str:
    """Stable SHA-256 of the trimmed rule text. Used as the cache key."""
    normalized = (text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _ensure_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_rule_embeddings (
            text_hash TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector_blob BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _vector_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_vector(blob: bytes, dim: int) -> list[float]:
    if not blob:
        return []
    return list(struct.unpack(f"<{dim}f", blob))


def _cache_get(conn: sqlite3.Connection, h: str) -> list[float] | None:
    try:
        row = conn.execute(
            "SELECT dim, vector_blob FROM prompt_rule_embeddings "
            "WHERE text_hash = ? AND model = ?",
            (h, EMBED_MODEL),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    try:
        return _blob_to_vector(row["vector_blob"], int(row["dim"]))
    except Exception:
        return None


def _cache_put(conn: sqlite3.Connection, h: str, vec: list[float]) -> None:
    conn.execute(
        """
        INSERT INTO prompt_rule_embeddings (text_hash, model, dim, vector_blob)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(text_hash) DO UPDATE SET
            model = excluded.model,
            dim = excluded.dim,
            vector_blob = excluded.vector_blob
        """,
        (h, EMBED_MODEL, len(vec), _vector_to_blob(vec)),
    )
    conn.commit()


def embed_rule(text: str) -> list[float]:
    """Return the embedding vector for ``text``, using the SQLite cache.

    Empty / whitespace-only inputs return an empty vector and never call
    out to the embedding service. The first cache miss triggers one
    network call; subsequent calls for the same trimmed text are free.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    h = _rule_hash(cleaned)
    with get_conn() as conn:
        _ensure_cache_table(conn)
        cached = _cache_get(conn, h)
        if cached is not None:
            return cached
    try:
        vector = embed([cleaned], input_type="passage")[0]
    except Exception as exc:
        _log.warning("embed_rule failed for hash=%s: %s", h[:10], exc)
        return []
    if not vector:
        return []
    with get_conn() as conn:
        _ensure_cache_table(conn)
        try:
            _cache_put(conn, h, list(vector))
        except Exception as exc:  # noqa: BLE001 — cache failure is non-fatal
            _log.warning("embed_rule cache write failed: %s", exc)
    return list(vector)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def cosine_search(
    query_text: str, candidates: Iterable[dict[str, Any]]
) -> tuple[float, dict[str, Any] | None]:
    """Find the candidate dict whose ``text`` is closest to ``query_text``.

    Returns ``(best_score, best_candidate)``; if every candidate is empty
    or the embed call fails, returns ``(0.0, None)``. Never raises — the
    analyzer pipeline must keep working even if the embedding service is
    unreachable.
    """
    query_vec = embed_rule(query_text)
    if not query_vec:
        return 0.0, None
    best_score = 0.0
    best_candidate: dict[str, Any] | None = None
    for cand in candidates or []:
        cand_text = str(cand.get("text") or "").strip()
        if not cand_text:
            continue
        cand_vec = embed_rule(cand_text)
        if not cand_vec:
            continue
        score = _cosine(query_vec, cand_vec)
        if score > best_score:
            best_score = score
            best_candidate = cand
    return best_score, best_candidate


def cache_size() -> tuple[int, int]:
    """Diagnostic: return ``(row_count, total_blob_bytes)`` for the cache."""
    try:
        with get_conn() as conn:
            _ensure_cache_table(conn)
            row = conn.execute(
                "SELECT COUNT(*) AS rows, COALESCE(SUM(LENGTH(vector_blob)), 0) AS bytes "
                "FROM prompt_rule_embeddings"
            ).fetchone()
    except Exception:
        return 0, 0
    if not row:
        return 0, 0
    return int(row["rows"] or 0), int(row["bytes"] or 0)
