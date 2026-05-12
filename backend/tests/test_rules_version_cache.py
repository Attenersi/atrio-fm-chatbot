"""Verify the active-overrides cache is keyed on meta.rules_version.

This is the multi-worker safety net: when worker A applies an override and
bumps `meta.rules_version`, worker B's next call to
`get_active_prompt_overrides` must return the fresh snapshot rather than
its stale per-process copy.

We test the cache logic with mocks instead of a real SQLite file so the
test is hermetic and doesn't fight the developer's `tickets.db` or
Windows file locking.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import database as db  # noqa: E402


class _StubConn:
    """Stand-in for sqlite3 connection just rich enough for the cache code path."""

    def __init__(self):
        self.exec_calls = []

    def execute(self, *args, **kwargs):
        self.exec_calls.append((args, kwargs))
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        return cursor

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RulesVersionCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset the module-level snapshot before every test so prior runs
        # cannot leak into ours.
        db._active_overrides_cache["version"] = None
        db._active_overrides_cache["data"] = []

    def test_snapshot_refreshes_when_version_bumps(self) -> None:
        versions = iter(["v1", "v1", "v2"])
        with patch.object(db, "get_rules_version", side_effect=lambda: next(versions)), \
             patch.object(db, "get_conn", return_value=_StubConn()):
            first = db.get_active_prompt_overrides()
            self.assertEqual(first, [])
            self.assertEqual(db._active_overrides_cache["version"], "v1")

            second = db.get_active_prompt_overrides()
            self.assertEqual(second, [])
            self.assertEqual(db._active_overrides_cache["version"], "v1")

            third = db.get_active_prompt_overrides()
            self.assertEqual(third, [])
            self.assertEqual(
                db._active_overrides_cache["version"],
                "v2",
                "version bump must trigger a fresh read on the next call",
            )

    def test_snapshot_reuses_when_version_unchanged(self) -> None:
        get_conn_mock = MagicMock(return_value=_StubConn())
        with patch.object(db, "get_rules_version", return_value="v-stable"), \
             patch.object(db, "get_conn", get_conn_mock):
            db.get_active_prompt_overrides()
            db.get_active_prompt_overrides()
            db.get_active_prompt_overrides()

        self.assertEqual(
            get_conn_mock.call_count,
            1,
            "constant rules_version should result in a single SQL fetch",
        )

    def test_force_refresh_bypasses_cache(self) -> None:
        get_conn_mock = MagicMock(return_value=_StubConn())
        with patch.object(db, "get_rules_version", return_value="v1"), \
             patch.object(db, "get_conn", get_conn_mock):
            db.get_active_prompt_overrides()
            db.get_active_prompt_overrides(force_refresh=True)
            db.get_active_prompt_overrides(force_refresh=True)

        self.assertEqual(
            get_conn_mock.call_count,
            3,
            "force_refresh must always re-execute the SELECT",
        )


if __name__ == "__main__":
    unittest.main()
