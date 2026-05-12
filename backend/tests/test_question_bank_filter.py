"""Tests for question-bank analyzer filtering."""

from __future__ import annotations

import unittest

from app.question_bank import filter_payload_by_claimed_examples


class TestQuestionBankFilter(unittest.TestCase):
    def test_removes_group_when_all_affected_claimed(self) -> None:
        payload = {
            "groups": [
                {
                    "type": "tone",
                    "affected_ids": [10, 11],
                    "suggested_change": "rule",
                }
            ],
            "rag_suggestions": [],
        }
        out = filter_payload_by_claimed_examples(payload, {10, 11})
        self.assertEqual(out["groups"], [])
        self.assertEqual(out.get("question_claim_hidden"), 1)
        self.assertEqual(len(out.get("question_claim_matches") or []), 1)

    def test_keeps_group_when_partial_claim(self) -> None:
        payload = {
            "groups": [{"type": "tone", "affected_ids": [1, 2], "suggested_change": "r"}],
            "rag_suggestions": [],
        }
        out = filter_payload_by_claimed_examples(payload, {1})
        self.assertEqual(len(out["groups"]), 1)

    def test_empty_claimed_returns_same_structure(self) -> None:
        payload = {
            "groups": [{"type": "tone", "affected_ids": [5], "suggested_change": "r"}],
            "rag_suggestions": [{"type": "rag", "description": "d", "affected_ids": [5]}],
        }
        out = filter_payload_by_claimed_examples(payload, set())
        self.assertEqual(len(out["groups"]), 1)
        self.assertEqual(len(out["rag_suggestions"]), 1)


if __name__ == "__main__":
    unittest.main()
