"""Tests for optional ``issues`` array in chat LLM JSON parsing."""
from __future__ import annotations

import json
import unittest

from app.classifier import parse_llm_json


class ParseIssuesTests(unittest.TestCase):
    def test_empty_issues_default(self) -> None:
        raw = json.dumps(
            {
                "category": "General",
                "priority": "NORMAL",
                "department": "Facility Management",
                "in_scope": "YES",
                "grounded": "YES",
                "query_type": "INFORMATIONAL",
                "create_ticket": "NO",
                "issue_summary": "test",
                "response": "ok",
            }
        )
        out = parse_llm_json(raw)
        self.assertEqual(out["issues"], [])

    def test_parses_and_dedupes_issues(self) -> None:
        raw = json.dumps(
            {
                "category": "General",
                "priority": "HIGH",
                "department": "Facility Management",
                "in_scope": "YES",
                "grounded": "YES",
                "query_type": "INCIDENT",
                "create_ticket": "YES",
                "issue_summary": "both",
                "response": "ok",
                "issues": [
                    {
                        "issue_summary": "Leak in bathroom",
                        "category": "Plumbing",
                        "priority": "HIGH",
                        "department": "Facility Management",
                        "create_ticket": "YES",
                    },
                    {
                        "issue_summary": "leak in bathroom",
                        "category": "Plumbing",
                        "priority": "NORMAL",
                        "create_ticket": "YES",
                    },
                    {
                        "issue_summary": "Hallway lights out",
                        "category": "Electrical",
                        "priority": "NORMAL",
                        "create_ticket": "YES",
                    },
                ],
            }
        )
        out = parse_llm_json(raw)
        self.assertEqual(len(out["issues"]), 2)
        summaries = {i["issue_summary"] for i in out["issues"]}
        self.assertIn("Leak in bathroom", summaries)
        self.assertIn("Hallway lights out", summaries)


if __name__ == "__main__":
    unittest.main()
