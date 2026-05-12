"""Tests for DB-backed FM base system prompt (``rag_system_prompt_head_override``)."""

from __future__ import annotations

import gc
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSystemPromptHeadOverride(unittest.TestCase):
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

    def test_override_roundtrip_and_effective_head(self) -> None:
        from app.rag import SYSTEM_PROMPT_HEAD, get_effective_system_prompt_head

        self.assertIsNone(self.db.get_rag_system_prompt_head_override())
        self.assertEqual(get_effective_system_prompt_head(), SYSTEM_PROMPT_HEAD)

        self.db.set_rag_system_prompt_head_override("CUSTOM_HEAD_BLOCK")
        self.assertEqual(
            self.db.get_rag_system_prompt_head_override(), "CUSTOM_HEAD_BLOCK"
        )
        self.assertEqual(get_effective_system_prompt_head(), "CUSTOM_HEAD_BLOCK")

        out = self.db.set_rag_system_prompt_head_override(None)
        self.assertTrue(out.get("using_builtin"))
        self.assertIsNone(self.db.get_rag_system_prompt_head_override())
        self.assertEqual(get_effective_system_prompt_head(), SYSTEM_PROMPT_HEAD)

    def test_clear_whitespace_string(self) -> None:
        from app.rag import get_effective_system_prompt_head

        self.db.set_rag_system_prompt_head_override("x")
        self.db.set_rag_system_prompt_head_override("   ")
        self.assertIsNone(self.db.get_rag_system_prompt_head_override())
        self.assertNotEqual(get_effective_system_prompt_head(), "x")


if __name__ == "__main__":
    unittest.main()
