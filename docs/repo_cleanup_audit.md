# Repo Cleanup Audit (No-Delete Pass)

This audit focuses on safe cleanup decisions without deleting files.

## High confidence candidates

- `frontend/.next/`
- `frontend/.next-dev/`
- `.cursor/debug-*.log`

Reason: generated/local runtime artifacts, no source value.

## Medium confidence candidates

- `backend/organize_test_files.py` — removed; use `backend/scripts/organize_test_files.py` directly (`python -m backend.scripts.organize_test_files`)
- `new_batches_question/*` (ad-hoc input batches)
- `backend/tests/suites/28.04.2026, weird top10 ids.txt` (ephemeral helper list)

Reason: likely one-off workflow files. Keep until archived.

## Low confidence candidates

- historical suites in `backend/tests/suites`
- root reference assets like `atrio_*.jsx`

Reason: possibly still useful for regressions or manual product/reference work.

## Keep (source-of-truth or derived artifacts)

- `backend/data/fine_tuning_v1_candidates.jsonl` (canonical in current workflow)
- `backend/data/fine_tuning_v1_train.jsonl`
- `backend/data/fine_tuning_v1_review.csv`
- `backend/data/fine_tuning_v1_manifest.json`

## Decision

- No immediate deletes.
- Move toward archive/baseline structure first.
