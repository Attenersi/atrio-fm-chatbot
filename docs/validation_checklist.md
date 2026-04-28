# Documentation and Training-Data Validation Checklist

Use this checklist before marking a release/documentation update as complete.

## Documentation quality

- Root `README.md` includes quick start and links to all role guides.
- `docs/README_developers.md` reflects real commands and file paths.
- `docs/README_managers.md` matches current admin capabilities (not future-only features).
- `docs/README_users.md` clearly explains scope, ticket behavior, and follow-ups.
- `docs/fine_tuning_data.md` includes canonical example and schema definitions.

## Backend integrity

- `backend/app/main.py` and `backend/app/database.py` compile without errors.
- App startup initializes `training_examples` table.
- Chat endpoints continue to return normal payload when training-log insert fails.
- Existing ticket and knowledge-gap behavior is unchanged.

## Training data capture

- Each chat query creates one `training_examples` row.
- `actual_output` includes category/priority/create_ticket/response/issue_summary.
- Context and source metadata are saved (`context_used`, `used_sources`, `context_count`).
- `correction_type` defaults to `pending`.

## Review and export workflow

- Admin can list examples with filters (`correction_type`, `user_role`).
- Admin can fetch a single example by ID.
- Admin can patch review fields (`correction_type`, `ideal_output`, `human_notes`, `context_used`, `reasoning`).
- Export endpoint returns NDJSON for selected correction types.
- Exported lines include canonical fields: `input`, `ideal_output`, `human_notes`, `correction_type`, `context_used`, `reasoning`.

## Testing and acceptance

- Run at least a short chat smoke test (informational + incident + follow-up).
- Confirm one example of each review state (`approved`, `edited`, `rejected`) can be set.
- Validate exported JSONL parses line-by-line.
- Re-run a small RAG subset to confirm no regression in normal chat/ticket flow.
