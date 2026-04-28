# Fine-Tuning Data Specification

This document defines how chat interactions are stored, reviewed, and exported
for future model fine-tuning.

## Goal

Capture every executed query as a training-example candidate, then curate it
into a high-quality JSONL dataset.

## Canonical training record

Each record should contain:

```json
{
  "input": "The AC in room 204 is making a loud grinding noise",
  "ideal_output": {
    "category": "HVAC",
    "priority": "HIGH",
    "create_ticket": true,
    "response": "Got it — I've created a ticket for the AC issue in room 204. Your HVAC team has been notified. Grinding noises often indicate a failing fan motor or loose component. Please avoid using the unit until a technician inspects it.",
    "issue_summary": "AC unit grinding noise, room 204, possible fan motor issue"
  },
  "human_notes": "Good classification. Response should mention not to use the unit — grinding can worsen the damage.",
  "correction_type": "approved",
  "context_used": ["02_hvac_systems.md chunk 4", "02_hvac_systems.md chunk 7"],
  "reasoning": "Grinding noise in AC = mechanical fault, not just comfort issue. HIGH not NORMAL because continued use can cause further damage."
}
```

## Stored operational fields (lineage and audit)

In addition to the canonical fields above, storage should retain:

- `id`
- `created_at`
- `user_id`
- `user_role`
- `query_type`
- `in_scope`
- `grounded`
- `actual_output` (assistant model output used at runtime)
- `ticket_created`
- `ticket_id`
- `used_sources` (raw source list from retrieval)
- `context_count`
- `model` (when available)
- `run_id` (optional grouping key for analysis batches)

These fields support traceability and filtering, but canonical export for
fine-tuning should include only supervised fields unless explicitly needed.

## Review states

`correction_type` allowed values:

- `approved` - model output accepted as ideal
- `edited` - reviewer modified one or more ideal fields
- `rejected` - unsuitable for training
- `pending` - default state before review

## JSONL export format

Exported file should be UTF-8 JSONL, one object per line.

Recommended export policy:

- include only `approved` and `edited`
- exclude `rejected` and `pending`
- require non-empty `input`
- require complete `ideal_output` (`category`, `priority`, `create_ticket`, `response`, `issue_summary`)

## Review workflow

1. System logs every query automatically.
2. Admin reviews candidate examples.
3. Admin sets `correction_type`.
4. For `edited`, admin adjusts `ideal_output`, adds `human_notes`, and `reasoning`.
5. Admin exports filtered JSONL for training.

## Data quality rules

- Keep `input` verbatim user phrasing (no paraphrasing).
- `ideal_output.response` must be concise, policy-compliant, and action-ready.
- `ideal_output.issue_summary` should be one sentence, operationally useful.
- Avoid contradictory labels (for example, `create_ticket=false` with incident-only response).
- For safety-adjacent cases, enforce consistent category/priority policy.

## Governance checklist before export

- Spot-check at least 50 recent approved/edited records.
- Verify class balance by category and priority.
- Verify low duplicate ratio.
- Verify no obvious PII leakage in `human_notes` or `reasoning`.
- Version the exported dataset with date and run ID.

## V1 backfill procedure (tickets + tests + logs)

Use admin endpoints to build the first combined dataset from:
- historical tickets (`tickets.db`)
- test report rows (`test_results_full.json`)
- existing runtime logs (`training_examples`)

Recommended sequence:

1. Backfill ticket-based seeds:
   - `POST /api/admin/training-examples/backfill/tickets`
2. Backfill test-based seeds:
   - `POST /api/admin/training-examples/backfill/tests?test_results_path=test_results_full.json`
3. Check deduplicated manifest:
   - `GET /api/admin/training-examples/v1/manifest`
4. Export preview files:
   - `GET /api/admin/training-examples/v1/export-jsonl?mode=candidates`
   - `GET /api/admin/training-examples/v1/export-csv`
5. Export train-ready JSONL:
   - `GET /api/admin/training-examples/v1/export-jsonl?mode=train`
6. Produce versioned files on disk:
   - `POST /api/admin/training-examples/v1/build-files`

## V1 file outputs

`POST /api/admin/training-examples/v1/build-files` writes:
- `data/fine_tuning_v1_candidates.jsonl`
- `data/fine_tuning_v1_review.csv`
- `data/fine_tuning_v1_train.jsonl`
- `data/fine_tuning_v1_manifest.json`

## V1 acceptance checklist

- Manifest shows non-zero rows from all configured source types.
- `train_jsonl` contains only `approved` and `edited`.
- `review_csv` contains `pending` and `rejected` for human review.
- Dedup ratio is reported and reviewed.
- Safety categories are manually sampled before first fine-tuning run.
