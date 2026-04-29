# Repository Structure Guide

## Current target layout (minimal disruption)

- `backend/app` - runtime backend code
- `backend/scripts` - maintenance scripts and one-off helpers
- `backend/tests/suites` - active test suites
- `backend/tests/results` - generated test outputs
- `backend/tests/archive` - archived suites/results snapshots (non-active)
- `backend/docs_fm` - ingest source documents
- `backend/data` - local training/data artifacts (generated + canonical JSON-first store)
- `frontend/src` - frontend application code
- `docs` - product, operations, testing, and data documentation

## Folder ownership contracts

- Generated files should not be manually edited.
- Canonical review data currently lives in `backend/data/fine_tuning_v1_candidates.jsonl`.
- Result files from test runs must stay in `backend/tests/results`.
- Historical datasets/suites should be moved to `backend/tests/archive`, not deleted first.

## Naming conventions

- Suite files: `YYYY-MM-DD_<suite>_cases.json`
- Results: `YYYY-MM-DD_<run>_results.json`
- Fail-ID helpers: `YYYY-MM-DD_<run>_failed.txt`
