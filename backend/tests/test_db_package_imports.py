"""Phase-4 split: ``app.db`` package re-exports must stay in sync with
``app.database`` (the legacy single-file module that still owns the
implementations during the transition).

This test catches accidental drift: if someone deletes a function from
``app.database`` without updating the matching re-export in ``app.db.*``,
the import here will fail loudly.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class DbPackageReexportTests(unittest.TestCase):
    def test_package_imports_cleanly(self) -> None:
        from app import db  # noqa: F401

        for name in (
            "_conn",
            "audit",
            "cache",
            "eval",
            "llm_profiles",
            "meta",
            "overrides",
            "question_bank",
            "training",
            "users",
        ):
            self.assertIn(name, dir(db), f"missing submodule: {name}")

    def test_users_reexports_match_database(self) -> None:
        from app import database as legacy
        from app.db import users

        for name in users.__all__:
            self.assertIs(
                getattr(users, name),
                getattr(legacy, name),
                f"users.{name} drifted from app.database.{name}",
            )

    def test_overrides_reexports_match_database(self) -> None:
        from app import database as legacy
        from app.db import overrides

        for name in overrides.__all__:
            self.assertIs(
                getattr(overrides, name),
                getattr(legacy, name),
                f"overrides.{name} drifted from app.database.{name}",
            )

    def test_meta_and_audit_reexports(self) -> None:
        from app import database as legacy
        from app.db import audit, meta

        for mod in (audit, meta):
            for name in mod.__all__:
                self.assertIs(
                    getattr(mod, name),
                    getattr(legacy, name),
                    f"{mod.__name__}.{name} drifted from app.database.{name}",
                )

    def test_legacy_database_module_still_importable(self) -> None:
        from app import database  # noqa: F401

        self.assertTrue(hasattr(database, "init_db"))
        self.assertTrue(hasattr(database, "get_active_prompt_overrides"))


if __name__ == "__main__":
    unittest.main()
