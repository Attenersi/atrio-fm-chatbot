# Artifact Hygiene Policy

## Generated artifacts

Generated artifacts should not be treated as source code:

- `frontend/.next/`
- `frontend/.next-dev/`
- `backend/tests/results/*`
- local debug logs (`.cursor/debug-*.log`)

## Training artifacts

- Canonical review store: `backend/data/fine_tuning_v1_candidates.jsonl`
- Derived exports:
  - `backend/data/fine_tuning_v1_train.jsonl`
  - `backend/data/fine_tuning_v1_review.csv`
  - `backend/data/fine_tuning_v1_manifest.json`

## Rules

1. Keep canonical and derived artifacts in `backend/data` only.
2. Keep active test suites in `backend/tests/suites`.
3. Move stale historical suites/results to `backend/tests/archive` before considering deletion.
4. Do not write test outputs to backend root.
