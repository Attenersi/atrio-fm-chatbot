"""Phase-4 embedding-based dedup smoke tests.

We mock out the actual embedding service so the suite stays hermetic; the
goal is to verify the wiring (borderline band, cache call shape, threshold
plumbing), not the upstream NV embed quality.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import prompt_rule_embeddings as pre  # noqa: E402
from app import prompt_rule_similarity as prs  # noqa: E402


class CosineMath(unittest.TestCase):
    def test_orthogonal(self) -> None:
        self.assertAlmostEqual(pre._cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_identical(self) -> None:
        self.assertAlmostEqual(pre._cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)

    def test_empty_inputs(self) -> None:
        self.assertEqual(pre._cosine([], [1.0]), 0.0)
        self.assertEqual(pre._cosine([1.0, 0.0], [0.0, 0.0]), 0.0)


class CosineSearch(unittest.TestCase):
    def test_picks_best_candidate(self) -> None:
        # Map every text we expect into a tiny vector so we can predict
        # cosine outcomes deterministically.
        vectors = {
            "query": [1.0, 0.0],
            "perfect match": [1.0, 0.0],
            "orthogonal": [0.0, 1.0],
            "near": [0.9, 0.4358],
        }

        def fake_embed_rule(text: str) -> list[float]:
            return vectors.get(text.strip(), [])

        with patch.object(pre, "embed_rule", side_effect=fake_embed_rule):
            score, cand = pre.cosine_search(
                "query",
                [
                    {"source": "a", "text": "perfect match"},
                    {"source": "b", "text": "near"},
                    {"source": "c", "text": "orthogonal"},
                ],
            )
        self.assertGreater(score, 0.99)
        self.assertEqual(cand["source"], "a")

    def test_returns_zero_when_query_unembeddable(self) -> None:
        with patch.object(pre, "embed_rule", return_value=[]):
            score, cand = pre.cosine_search("query", [{"source": "x", "text": "y"}])
        self.assertEqual(score, 0.0)
        self.assertIsNone(cand)


class FindDuplicateRuleEmbeddingFallback(unittest.TestCase):
    def setUp(self) -> None:
        self._patches = [
            patch.object(prs, "EMBEDDING_DEDUP_ENABLED", True),
            patch.object(prs, "EMBEDDING_DEDUP_LOWER_BOUND", 0.30),
            patch.object(prs, "EMBEDDING_DEDUP_UPPER_BOUND", 0.85),
            patch.object(prs, "EMBEDDING_DEDUP_COSINE_THRESHOLD", 0.80),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def test_borderline_promoted_to_duplicate_when_cosine_high(self) -> None:
        rule = "Always escalate flooding to URGENT priority within 5 minutes."
        # An active override that overlaps a few tokens but stays below the
        # cheap thresholds — pushes the score into the borderline band so
        # the embedding fallback fires.
        active = [
            {
                "id": 7,
                "approved_change": (
                    "When tenants report flooding incidents, dispatch a "
                    "technician quickly to mitigate damage to property."
                ),
            }
        ]
        candidate_text = active[0]["approved_change"]

        with patch.object(
            prs,
            "_embedding_second_stage",
            return_value=(0.92, {"source": "active_override:7", "text": candidate_text}),
        ) as mock_embed:
            result = prs.find_duplicate_rule(rule, "## Rules", active_overrides=active)

        mock_embed.assert_called_once()
        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["match_type"], "embedding")
        self.assertEqual(result["source"], "active_override:7")
        self.assertGreaterEqual(float(result["score"]), 0.80)

    def test_borderline_kept_when_cosine_low(self) -> None:
        rule = "If user mentions broken elevator, mark HIGH priority."
        active = [
            {
                "id": 9,
                "approved_change": (
                    "Schedule annual chiller maintenance every spring season "
                    "before peak summer demand begins."
                ),
            }
        ]

        with patch.object(
            prs,
            "_embedding_second_stage",
            return_value=(0.42, {"source": "active_override:9", "text": active[0]["approved_change"]}),
        ):
            result = prs.find_duplicate_rule(rule, "## Rules", active_overrides=active)

        self.assertFalse(result["is_duplicate"])
        self.assertNotEqual(result["match_type"], "embedding")

    def test_outright_duplicate_short_circuits_embedding(self) -> None:
        rule = "Always create a ticket for any reported leak."

        with patch.object(prs, "_embedding_second_stage") as mock_embed:
            result = prs.find_duplicate_rule(
                rule,
                "- Always create a ticket for any reported leak.",
                active_overrides=[],
            )

        self.assertTrue(result["is_duplicate"])
        mock_embed.assert_not_called()

    def test_use_embedding_fallback_false_disables_second_stage(self) -> None:
        rule = "Borderline rule that nearly matches an existing one."
        with patch.object(prs, "_embedding_second_stage") as mock_embed:
            prs.find_duplicate_rule(
                rule,
                "- Borderline ish",
                active_overrides=[],
                use_embedding_fallback=False,
            )
        mock_embed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
