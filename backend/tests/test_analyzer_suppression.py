"""Unit tests for analyzer signal suppression and discard filtering."""

from __future__ import annotations

import unittest

from app.database import suppress_review_signals
from app.prompt_rule_similarity import filter_discarded_suggestions


class TestSuppressReviewSignals(unittest.TestCase):
    def test_empty_covered_preserves_groups(self) -> None:
        signals = {
            "total_signals": 2,
            "groups": [
                {
                    "type": "tone",
                    "count": 2,
                    "affected_ids": [1, 2],
                    "examples": [{"id": 1}, {"id": 2}],
                }
            ],
        }
        out = suppress_review_signals(signals, set())
        self.assertEqual(len(out["groups"]), 1)
        self.assertEqual(out["total_signals"], 2)

    def test_full_cover_removes_group(self) -> None:
        signals = {
            "total_signals": 2,
            "groups": [
                {
                    "type": "tone",
                    "count": 2,
                    "affected_ids": [1, 2],
                    "examples": [{"id": 1}, {"id": 2}],
                }
            ],
        }
        out = suppress_review_signals(signals, {1, 2})
        self.assertEqual(out["groups"], [])
        self.assertEqual(out["total_signals"], 0)

    def test_partial_cover_filters_lists(self) -> None:
        signals = {
            "total_signals": 3,
            "groups": [
                {
                    "type": "tone",
                    "count": 3,
                    "affected_ids": [1, 2, 3],
                    "examples": [{"id": 1}, {"id": 2}, {"id": 3}],
                }
            ],
        }
        out = suppress_review_signals(signals, {2})
        g = out["groups"][0]
        self.assertEqual(g["affected_ids"], [1, 3])
        self.assertEqual([e["id"] for e in g["examples"]], [1, 3])
        self.assertEqual(g["count"], 2)
        self.assertEqual(out["total_signals"], 2)


class TestFilterDiscardedSuggestions(unittest.TestCase):
    def test_near_duplicate_hidden(self) -> None:
        groups = [
            {
                "type": "hallucination",
                "suggested_change": "Never invent serial numbers for products.",
            }
        ]
        decisions = [
            {
                "id": 99,
                "error_type": "hallucination",
                "suggested_change": "Do not invent serial numbers for products.",
            }
        ]
        vis, hid = filter_discarded_suggestions(groups, decisions)
        self.assertEqual(vis, [])
        self.assertEqual(len(hid), 1)
        self.assertEqual(hid[0].get("decision_id"), 99)

    def test_different_text_visible(self) -> None:
        groups = [
            {"type": "tone", "suggested_change": "Use a warmer greeting."}
        ]
        decisions = [
            {
                "id": 1,
                "error_type": "tone",
                "suggested_change": "Always cite ticket SLA in hours.",
            }
        ]
        vis, hid = filter_discarded_suggestions(groups, decisions)
        self.assertEqual(len(vis), 1)
        self.assertEqual(hid, [])

    def test_error_type_mismatch_not_matched(self) -> None:
        groups = [
            {
                "type": "tone",
                "suggested_change": "Never invent serial numbers for products.",
            }
        ]
        decisions = [
            {
                "id": 1,
                "error_type": "hallucination",
                "suggested_change": "Do not invent serial numbers for products.",
            }
        ]
        vis, hid = filter_discarded_suggestions(groups, decisions)
        self.assertEqual(len(vis), 1)
        self.assertEqual(hid, [])


if __name__ == "__main__":
    unittest.main()
