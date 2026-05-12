"""Tests for prompt override list enrichment with supporting examples."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.training_quality_analysis_enrich import (
    SUPPORTING_EXAMPLES_CAP,
    enrich_prompt_override_rows,
)


def _row(
    oid: int,
    ids: list[int],
) -> dict:
    return {
        "id": oid,
        "affected_example_ids": ids,
        "error_type": "tone",
        "approved_change": "x",
    }


def _db_item(eid: int) -> dict:
    return {
        "id": eid,
        "input_text": f"q{eid}",
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


class TestEnrichPromptOverrideRows(unittest.TestCase):
    @patch(
        "app.training_quality_analysis_enrich.get_training_examples_review_items_by_ids"
    )
    def test_batch_fetch_and_order(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = {1: _db_item(1), 2: _db_item(2), 3: _db_item(3)}
        rows = [_row(10, [2, 1]), _row(11, [3])]
        out = enrich_prompt_override_rows(rows)
        mock_fetch.assert_called_once_with([2, 1, 3])
        self.assertEqual(out[0]["supporting_examples"][0]["id"], 2)
        self.assertEqual(out[0]["supporting_examples"][1]["id"], 1)
        self.assertEqual(out[1]["supporting_examples"][0]["id"], 3)

    @patch(
        "app.training_quality_analysis_enrich.get_training_examples_review_items_by_ids"
    )
    def test_cap_per_override(self, mock_fetch: MagicMock) -> None:
        n = SUPPORTING_EXAMPLES_CAP + 5
        ids = list(range(n))
        mock_fetch.return_value = {i: _db_item(i) for i in ids}
        out = enrich_prompt_override_rows([_row(1, ids)])
        self.assertEqual(len(out[0]["supporting_examples"]), SUPPORTING_EXAMPLES_CAP)
        self.assertEqual(out[0]["supporting_examples_omitted_count"], 5)

    def test_empty_rows(self) -> None:
        self.assertEqual(enrich_prompt_override_rows([]), [])


if __name__ == "__main__":
    unittest.main()
