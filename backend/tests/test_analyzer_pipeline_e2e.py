"""Phase-4 end-to-end test for the analyzer post-processing pipeline.

Pins the contract that the analyzer LLM output flows through every hidden
filter — question-bank claims, duplicate-rule, reviewer discards — before
reaching the admin UI as a single response payload with one
``hidden_suggestions`` array.

We mock the LLM and the DB-backed claim/decision sources so the test is
hermetic; the production pipeline is exercised exactly as ``main.py``
runs it through ``_finalize_analysis_response``.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import database as app_database  # noqa: E402
from app import main as app_main  # noqa: E402


SYSTEM_PROMPT = (
    "You are an FM assistant.\n\n"
    "## Rules\n"
    "- Always create a ticket for any reported leak.\n"
    "- Reply in the same language the user used.\n"
)


ACTIVE_OVERRIDES = [
    {
        "id": 11,
        "approved_change": "Always escalate flooding to URGENT priority within 5 minutes.",
    }
]


DISCARD_DECISIONS = [
    {
        "id": 99,
        "error_type": "tone",
        "suggested_change": "Use a warmer greeting in the first message.",
    }
]


# Simulated analyzer LLM output: four groups + one RAG suggestion.
ANALYZER_PAYLOAD = {
    "model": "test-model",
    "generated_at": "2026-05-10T00:00:00+00:00",
    "groups": [
        {
            "type": "tone",
            "suggested_change": "Open with a warmer greeting on the first message.",
            "confidence": 0.7,
            "affected_ids": [201],
            "rationale": "Reviewer flagged a curt opener.",
        },
        {
            "type": "ticketing",
            "suggested_change": "Always create a ticket whenever the user reports a leak.",
            "confidence": 0.8,
            "affected_ids": [301],
            "rationale": "",
        },
        {
            "type": "priority",
            "suggested_change": "Treat flooding reports as URGENT and dispatch within 5 minutes.",
            "confidence": 0.9,
            "affected_ids": [401, 402],
            "rationale": "",
        },
        {
            "type": "policy",
            "suggested_change": "When tenant asks about pet policy, redirect to property manager.",
            "confidence": 0.8,
            "affected_ids": [501],
            "rationale": "Out-of-scope routing.",
        },
    ],
    "rag_suggestions": [],
}


class AnalyzerPipelineE2E(unittest.TestCase):
    def test_one_visible_three_hidden(self) -> None:
        # The "priority" suggestion (affected_ids=[401, 402]) is fully
        # claimed by the active override → question_bank_claimed.
        # The "ticketing" suggestion is a near-duplicate of an existing
        # system-prompt rule → duplicate_rule.
        # The "tone" suggestion matches a reviewer-discarded decision →
        # reviewer_discarded.
        # Only the "policy" suggestion should remain visible.
        with patch.object(
            app_database,
            "get_question_bank_claimed_example_ids",
            return_value={401, 402},
        ):
            response = app_main._finalize_analysis_response(
                ANALYZER_PAYLOAD,
                SYSTEM_PROMPT,
                ACTIVE_OVERRIDES,
                DISCARD_DECISIONS,
            )

        visible_types = [g["type"] for g in response["groups"]]
        self.assertEqual(
            visible_types,
            ["policy"],
            f"expected only the policy group to survive, got {visible_types}",
        )

        hidden = response["hidden_suggestions"]
        reasons = sorted(h["reason"] for h in hidden)
        self.assertEqual(
            reasons,
            ["duplicate_rule", "question_bank_claimed", "reviewer_discarded"],
            f"expected one of each hidden reason, got {reasons}",
        )

        # The integer counters must match the array contents (dashboard
        # headline relies on these even now that the per-reason arrays
        # are gone).
        by_reason = {h["reason"]: h for h in hidden}
        self.assertEqual(response["question_claim_hidden"], 1)
        self.assertEqual(response["duplicate_suggestions_hidden"], 1)
        self.assertEqual(response["discarded_suggestions_hidden"], 1)

        self.assertIn("flooding", by_reason["question_bank_claimed"]["suggested_change"].lower())
        self.assertIn("leak", by_reason["duplicate_rule"]["suggested_change"].lower())
        self.assertIn("greeting", by_reason["reviewer_discarded"]["suggested_change"].lower())

        # The reviewer-discarded entry must include the decision id so the
        # UI can deep-link back to the original suggestion record.
        self.assertEqual(by_reason["reviewer_discarded"]["decision_id"], 99)

    def test_no_hits_keeps_everything_visible(self) -> None:
        with patch.object(
            app_database,
            "get_question_bank_claimed_example_ids",
            return_value=set(),
        ):
            response = app_main._finalize_analysis_response(
                ANALYZER_PAYLOAD,
                "## Rules\n",
                [],
                [],
            )
        self.assertEqual(len(response["groups"]), 4)
        self.assertEqual(response["hidden_suggestions"], [])
        self.assertEqual(response["question_claim_hidden"], 0)
        self.assertEqual(response["duplicate_suggestions_hidden"], 0)
        self.assertEqual(response["discarded_suggestions_hidden"], 0)


if __name__ == "__main__":
    unittest.main()
