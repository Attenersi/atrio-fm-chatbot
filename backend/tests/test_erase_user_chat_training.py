"""Tests for GDPR-oriented erasure of chat + training rows by user_id."""

from __future__ import annotations

import gc
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEraseUserChatTraining(unittest.TestCase):
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

    def test_erase_removes_chat_training_and_events_for_user_only(self) -> None:
        u1 = self.db.create_user_account("erase_subject", "secret12")
        u2 = self.db.create_user_account("other_user", "secret12")
        uid1 = int(u1["id"])
        uid2 = int(u2["id"])
        self.db.append_chat_exchange(uid1, "hello", "hi there")
        self.db.append_chat_exchange(uid2, "stay", "preserved")
        ex = self.db.create_training_example(
            input_text="leak test",
            actual_output={},
            user_id=uid1,
            user_role="user",
            query_type="q",
            in_scope="y",
            grounded="y",
            context_used=[],
            used_sources=[],
            context_count=0,
            ticket_created=False,
            ticket_id=None,
            source_type="chat_log",
            source_id="erase-test-1",
            source_ref="",
        )
        self.db.create_training_example(
            input_text="other",
            actual_output={},
            user_id=uid2,
            user_role="user",
            query_type="q",
            in_scope="y",
            grounded="y",
            context_used=[],
            used_sources=[],
            context_count=0,
            ticket_created=False,
            ticket_id=None,
            source_type="chat_log",
            source_id="erase-test-2",
            source_ref="",
        )
        ex_id = int(ex["id"])
        now = self.db._utc_now_iso()
        with self.db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO training_question_prompt_events (
                    training_example_id, event_type, override_id,
                    analysis_cache_key, ref_json, created_at
                )
                VALUES (?, 'override_applied', NULL, NULL, '{}', ?)
                """,
                (ex_id, now),
            )
            conn.commit()

        counts = self.db.erase_user_chat_and_training_data(uid1)

        self.assertGreaterEqual(counts["training_examples_deleted"], 1)
        self.assertGreaterEqual(counts["chat_threads_deleted"], 1)
        self.assertGreaterEqual(counts["chat_messages_deleted"], 1)
        self.assertGreaterEqual(counts["training_question_prompt_events_deleted"], 1)

        with self.db.get_conn() as conn:
            n_ex = conn.execute(
                "SELECT COUNT(*) FROM training_examples WHERE user_id = ?",
                (uid1,),
            ).fetchone()[0]
            n_ex2 = conn.execute(
                "SELECT COUNT(*) FROM training_examples WHERE user_id = ?",
                (uid2,),
            ).fetchone()[0]
            n_msg = conn.execute(
                """
                SELECT COUNT(*) FROM chat_messages m
                JOIN chat_threads t ON m.thread_id = t.id
                WHERE t.user_id = ?
                """,
                (uid1,),
            ).fetchone()[0]
            n_ev = conn.execute(
                """
                SELECT COUNT(*) FROM training_question_prompt_events t
                JOIN training_examples e ON e.id = t.training_example_id
                WHERE e.user_id = ?
                """,
                (uid1,),
            ).fetchone()[0]

        self.assertEqual(int(n_ex), 0)
        self.assertEqual(int(n_msg), 0)
        self.assertEqual(int(n_ev), 0)
        self.assertGreaterEqual(int(n_ex2), 1)


if __name__ == "__main__":
    unittest.main()
