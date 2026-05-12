# Initial acceptance checklist

Run **once** when you first ship the training-data / admin-review baseline, after **major** database or capture-schema changes, or when you need a full documentation audit before a production cut.

It is intentionally heavier than the [every-deploy release checklist](validation_release.md).

## Documentation quality

- [`documentation_map.md`](documentation_map.md) is complete and every linked role guide opens without broken paths.
- [`README_developers.md`](README_developers.md) matches real commands, Docker workflow, and file paths.
- [`README_managers.md`](README_managers.md) matches current admin capabilities (not aspirational-only features).
- [`README_users.md`](README_users.md) clearly explains scope, ticket behavior, and follow-ups.
- [`fine_tuning_data.md`](fine_tuning_data.md) includes canonical examples and schema definitions for exports.

## Backend and schema integrity

- `backend/app/main.py` and `backend/app/database.py` load without syntax/import errors in your target environment.
- On a **fresh** or migrated database, app startup creates or migrates the `training_examples` table and related training-quality tables as expected.
- Chat endpoints still return a normal user-facing payload if inserting a `training_examples` row fails (logging path must not break the response).
- Existing ticket and knowledge-gap behavior matches the documented baseline (no accidental regression in classification or CRUD).

## Training data capture (full verification)

- Each chat query that should be logged creates **one** `training_examples` row under normal conditions.
- `actual_output` (or stored JSON) includes category, priority, create-ticket flag, response, and issue summary as designed.
- Context and source metadata are persisted (`context_used`, `used_sources`, `context_count` or current equivalents).
- `correction_type` defaults to `pending` for new rows.

## Review and export workflow

- Admin can list examples with filters (`correction_type`, `user_role`, etc.).
- Admin can fetch a single example by ID.
- Admin can patch review fields (`correction_type`, `ideal_output`, `human_notes`, `context_used`, `reasoning` or current API fields).
- Export endpoint returns NDJSON for selected correction types.
- Exported lines include the canonical fields your fine-tuning pipeline expects: `input`, `ideal_output`, `human_notes`, `correction_type`, `context_used`, `reasoning` (or documented equivalents).

## Testing and sign-off

- Run at least one chat smoke path per major intent: informational, incident-style, and a follow-up turn.
- Confirm each review outcome you support (`approved`, `edited`, `rejected`, …) can be set and persists.
- Validate exported JSONL parses **line-by-line** without manual fixes.
- Run a **meaningful** RAG / chat regression (not only a single happy path) before calling the baseline accepted.

When this passes, routine deploys only need [`validation_release.md`](validation_release.md) unless you change the same subsystems again.
