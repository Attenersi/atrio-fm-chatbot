"""SQLite meta override for retrieval depth (``effective_rag_top_k``)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7", 7),
        ("1", 1),
        ("24", 24),
        ("999", 24),
        ("0", 1),
        ("-5", 1),
    ],
)
def test_effective_rag_top_k_clamps(raw: str, expected: int) -> None:
    with patch("app.rag.get_meta", return_value=raw):
        from app.rag import effective_rag_top_k

        assert effective_rag_top_k() == expected


def test_effective_rag_top_k_invalid_meta_falls_back() -> None:
    with patch("app.rag.get_meta", return_value="not-an-int"):
        from app.rag import effective_rag_top_k

        assert isinstance(effective_rag_top_k(), int)
        assert effective_rag_top_k() >= 1


def test_effective_rag_top_k_empty_meta_falls_back() -> None:
    with patch("app.rag.get_meta", return_value=""):
        from app.rag import effective_rag_top_k

        assert isinstance(effective_rag_top_k(), int)
