"""Tests for analyzer payload enrichment with supporting examples."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.training_quality_analysis_enrich import (
    SUPPORTING_EXAMPLES_CAP,
    build_example_lookup_from_signals,
    collect_affected_ids_from_analysis_payload,
    enrich_analysis_payload_with_supporting_examples,
)


class TestBuildLookup(unittest.TestCase):
    def test_first_example_wins(self) -> None:
        signals = {
            "groups": [
                {"examples": [{"id": 1, "input_text": "a"}]},
                {"examples": [{"id": 1, "input_text": "b"}]},
            ]
        }
        lu = build_example_lookup_from_signals(signals)
        self.assertEqual(lu[1]["input_text"], "a")


class TestCollectAffected(unittest.TestCase):
    def test_order_unique_across_groups_and_rag(self) -> None:
        payload = {
            "groups": [{"affected_ids": [3, 1]}],
            "rag_suggestions": [{"affected_ids": [1, 2]}],
        }
        self.assertEqual(
            collect_affected_ids_from_analysis_payload(payload),
            [3, 1, 2],
        )


class TestEnrich(unittest.TestCase):
    def test_cap_and_truncation_count(self) -> None:
        n = 20
        ids = list(range(n))
        payload = {
            "groups": [{"type": "x", "affected_ids": ids, "suggested_change": "s"}],
            "rag_suggestions": [],
        }
        ex = []
        for i in range(n):
            ex.append(
                {
                    "id": i,
                    "input_text": str(i),
                    "actual_output": {},
                    "ideal_output": {},
                    "human_notes": "",
                    "reasoning": "",
                    "correction_type": "edited",
                    "mismatch_fields": [],
                    "expected_payload": {},
                    "actual_payload": {},
                    "source_type": "",
                }
            )
        signals = {"groups": [{"examples": ex}]}
        out = enrich_analysis_payload_with_supporting_examples(payload, signals)
        g = out["groups"][0]
        self.assertEqual(len(g["supporting_examples"]), SUPPORTING_EXAMPLES_CAP)
        self.assertEqual(
            g["supporting_examples_omitted_count"],
            n - SUPPORTING_EXAMPLES_CAP,
        )
        # Order follows affected_ids
        self.assertEqual(g["supporting_examples"][0]["id"], 0)

    @patch(
        "app.training_quality_analysis_enrich.get_training_examples_review_items_by_ids"
    )
    def test_fetches_missing_ids(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = {
            99: {
                "id": 99,
                "input_text": "from db",
                "actual_output": {},
                "ideal_output": {},
                "human_notes": "n",
                "reasoning": "",
                "correction_type": "edited",
                "mismatch_fields": [],
                "expected_payload": {},
                "actual_payload": {},
                "source_type": "",
            }
        }
        payload = {
            "groups": [
                {"type": "t", "affected_ids": [99], "suggested_change": "x"}
            ],
            "rag_suggestions": [],
        }
        signals: dict = {"groups": []}
        out = enrich_analysis_payload_with_supporting_examples(payload, signals)
        mock_fetch.assert_called_once()
        row = out["groups"][0]["supporting_examples"][0]
        self.assertFalse(row.get("missing"))
        self.assertEqual(row.get("input"), "from db")


if __name__ == "__main__":
    unittest.main()
