# Move Matrix (Low-Risk)

This matrix lists intended moves with compatibility notes.

| Old path | New path | Status | Compatibility |
|---|---|---|---|
| `backend/organize_test_files.py` | `backend/scripts/organize_test_files.py` | done | old wrapper removed; use `python -m backend.scripts.organize_test_files` |
| root-level ad-hoc test inputs (`new_batches_question/*`) | `backend/tests/archive/sources/new_batches_question/*` | planned | keep original until archive pass |
| historical dated suites in `backend/tests/suites` | `backend/tests/archive/suites/*` | planned | keep active suites in `tests/suites` |
| old generated results in `backend/tests/results` | `backend/tests/archive/results/*` | planned | no delete, archive only |

## Migration principle

- Move first, delete later (after at least 1-2 stable test cycles).
- Keep wrappers for moved scripts if referenced in old notes/runbooks.
