"""Smoke tests for prompt consolidator (no LLM)."""
from __future__ import annotations

import unittest

from app.prompt_consolidator import (
    CONSOLIDATE_LINE_CLUSTER_THRESHOLD,
    _SYSTEM,
    build_consolidator_user_message,
    cluster_consolidator_lines,
)
from app.prompt_rule_similarity import rule_similarity


class TestConsolidatorPrompt(unittest.TestCase):
    def test_system_prompt_forbids_verbatim_paste(self) -> None:
        low = _SYSTEM.lower()
        self.assertIn("not to concatenate", low)
        self.assertIn("verbatim", low)
        self.assertIn("rewrite", low)

    def test_rule_similarity_smoke(self) -> None:
        a = "When user reports smoke, set priority to URGENT."
        b = "If the user mentions smoke, use URGENT priority."
        self.assertGreater(rule_similarity(a, b), 0.35)

    def test_clustering_merges_similar_lines(self) -> None:
        lines = [
            (1, "When user reports smoke, set priority to URGENT."),
            (2, "If the user mentions smoke, use URGENT priority."),
            (3, "Always greet the user by name."),
        ]
        clusters = cluster_consolidator_lines(
            lines, threshold=CONSOLIDATE_LINE_CLUSTER_THRESHOLD
        )
        self.assertGreaterEqual(len(clusters), 2)
        # smoke lines should land in one group
        smoke_cluster = next(
            (c for c in clusters if len(c) >= 2 and {1, 2} <= {x[0] for x in c}),
            None,
        )
        self.assertIsNotNone(smoke_cluster)

    def test_build_user_message_contains_groups(self) -> None:
        rows = [
            {
                "id": 10,
                "error_type": "category_mismatch",
                "approved_change": "Rule A about smoke.\nRule B duplicate smoke idea.",
                "rationale": "",
            },
        ]
        msg = build_consolidator_user_message(rows)
        self.assertIn("Group", msg)
        self.assertIn("override #10", msg)


if __name__ == "__main__":
    unittest.main()
