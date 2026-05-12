"""Tests for ``export_training_examples_jsonl`` filters and record shape."""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrainingExamplesExport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self._tmp.close()
        self._db_path = self._tmp.name
        self._db_patch = patch("app.database.SQLITE_DB_PATH", self._db_path)
        self._db_patch.start()
        self._refresh_patch = patch("app.database._auto_refresh_v1_dataset_files")
        self._refresh_patch.start()
        from app import database as db

        self.db = db
        db.init_db()

    def tearDown(self) -> None:
        self._refresh_patch.stop()
        self._db_patch.stop()
        self.db = None  # type: ignore[assignment]
        gc.collect()
        for path in (
            self._db_path,
            f"{self._db_path}-wal",
            f"{self._db_path}-shm",
        ):
            try:
                os.unlink(path)
            except OSError:
                pass

    def _seed_row(
        self,
        *,
        source_id: str,
        correction_type: str,
        created_at: str,
        input_text: str = "hello",
    ) -> int:
        row = self.db.create_training_example(
            input_text=input_text,
            actual_output={
                "category": "HVAC",
                "priority": "LOW",
                "create_ticket": False,
                "response": "resp",
                "issue_summary": "sum",
            },
            user_id=None,
            user_role="user",
            query_type="INFORMATIONAL",
            in_scope="YES",
            grounded="YES",
            context_used=[],
            used_sources=[],
            context_count=0,
            ticket_created=False,
            ticket_id=None,
            source_type="chat_log",
            source_id=source_id,
            source_ref="",
        )
        eid = int(row["id"])
        with self.db.get_conn() as conn:
            conn.execute(
                """
                UPDATE training_examples
                SET correction_type = ?, created_at = ?
                WHERE id = ?
                """,
                (correction_type, created_at, eid),
            )
            conn.commit()
        return eid

    def _lines(self, ndjson: str) -> list[dict]:
        out: list[dict] = []
        for line in ndjson.strip().split("\n"):
            if line.strip():
                out.append(json.loads(line))
        return out

    def test_correction_type_filter_and_id_created_at_shape(self) -> None:
        a = self._seed_row(
            source_id="e-a",
            correction_type="pending",
            created_at="2024-03-01T10:00:00+00:00",
            input_text="one",
        )
        b = self._seed_row(
            source_id="e-b",
            correction_type="edited",
            created_at="2024-09-15T12:00:00+00:00",
            input_text="two",
        )
        self._seed_row(
            source_id="e-c",
            correction_type="rejected",
            created_at="2024-01-01T08:00:00+00:00",
            input_text="three",
        )

        text = self.db.export_training_examples_jsonl(
            include_correction_types=["pending", "edited"]
        )
        rows = self._lines(text)
        self.assertEqual(len(rows), 2)
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {a, b})
        for r in rows:
            self.assertIn("id", r)
            self.assertIn("created_at", r)
            self.assertIn("ideal_output", r)
            self.assertEqual(r["ideal_output"]["category"], "HVAC")
            self.assertNotIn("actual_output", r)

    def test_id_range_and_specific_ids(self) -> None:
        x1 = self._seed_row(
            source_id="x-1",
            correction_type="pending",
            created_at="2024-06-01T00:00:00+00:00",
        )
        x2 = self._seed_row(
            source_id="x-2",
            correction_type="pending",
            created_at="2024-06-02T00:00:00+00:00",
        )
        x3 = self._seed_row(
            source_id="x-3",
            correction_type="pending",
            created_at="2024-06-03T00:00:00+00:00",
        )

        t1 = self.db.export_training_examples_jsonl(
            include_correction_types=["pending"],
            id_min=x2,
            id_max=x2,
        )
        self.assertEqual([r["id"] for r in self._lines(t1)], [x2])

        t2 = self.db.export_training_examples_jsonl(
            include_correction_types=["pending"],
            example_ids=[x1, x3],
            id_min=x1,
            id_max=x2,
        )
        self.assertEqual([r["id"] for r in self._lines(t2)], [x1])

    def test_created_bounds(self) -> None:
        self._seed_row(
            source_id="d-1",
            correction_type="approved",
            created_at="2024-01-10T00:00:00+00:00",
        )
        mid = self._seed_row(
            source_id="d-2",
            correction_type="approved",
            created_at="2024-06-01T00:00:00+00:00",
        )
        self._seed_row(
            source_id="d-3",
            correction_type="approved",
            created_at="2024-12-01T00:00:00+00:00",
        )

        text = self.db.export_training_examples_jsonl(
            include_correction_types=["approved"],
            created_after="2024-05-01T00:00:00+00:00",
            created_before="2024-07-01T00:00:00+00:00",
        )
        self.assertEqual([r["id"] for r in self._lines(text)], [mid])

    def test_include_actual_output(self) -> None:
        eid = self._seed_row(
            source_id="act-1",
            correction_type="pending",
            created_at="2024-01-01T00:00:00+00:00",
        )
        text = self.db.export_training_examples_jsonl(
            include_correction_types=["pending"],
            example_ids=[eid],
            include_actual_output=True,
        )
        rows = self._lines(text)
        self.assertEqual(len(rows), 1)
        self.assertIn("actual_output", rows[0])
        self.assertEqual(rows[0]["actual_output"]["response"], "resp")

    def test_invalid_correction_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.db.export_training_examples_jsonl(
                include_correction_types=["pending", "nope"]
            )


if __name__ == "__main__":
    unittest.main()
