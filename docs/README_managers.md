# Manager/Admin Guide

This guide maps "manager" responsibilities to the current `admin` role in the app.

## Access

- Sign in with an account that has role `admin`.
- Main work areas:
  - `/dashboard` - ticket metrics and operations
  - `/admin` - document, user, and knowledge-gap management

## Ticket operations

On dashboard you can:
- view all tickets
- filter by category/priority/status
- sort and paginate
- open ticket details
- change ticket status (`Open`, `In Progress`, `Resolved`)
- export current ticket dataset to CSV

## What to monitor daily

- Count of `URGENT` tickets
- Tickets stuck in `Open`
- Category spikes (Safety, Plumbing, HVAC)
- Recurring summaries (same issue pattern)

## Knowledge management

In Admin panel you can:
- list/edit/create/delete FM docs
- upload `.txt/.md/.csv/.pdf/.docx`
- run reindex after content updates
- review and resolve knowledge gaps

Recommended process:
1. Check new knowledge gaps.
2. Confirm missing/incorrect policy or data.
3. Add/patch document content.
4. Reindex.
5. Validate with targeted chat prompts or test subset.

## User administration

Admin panel supports:
- role changes (`user` / `admin`)
- activation/deactivation
- optional email management (notifications)

Guardrails:
- system always requires at least one active admin.

## Training-data review workflow

Admin endpoints and panel workflow support:
- reviewing logged training examples
- marking `approved`, `edited`, or `rejected`
- adding `human_notes`
- setting `ideal_output`
- exporting curated JSONL for fine-tuning

See data format and governance in `docs/fine_tuning_data.md`.

## Operational KPIs

Track separately:
- all-case pass rate (includes infrastructure effects)
- `api_ok_only` pass rate (model/logic quality)

Testing runbook: `backend/test_runbook.md`.
